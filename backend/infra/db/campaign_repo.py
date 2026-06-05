"""
Outreach campaign repository — campaigns, contacts, templates, batch send jobs,
and campaign files.
Implements domain/interfaces/repos.py::CampaignRepo.
"""
import json
import logging
from typing import Any, Optional

from backend.infra.db.pool import get_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outreach Campaigns
# ---------------------------------------------------------------------------

async def create_campaign(
    base_id: str,
    table_id: str,
    goal: str,
    mapping_id: Optional[int] = None,
    pitch_page_url: Optional[str] = None,
    pitch_page_label: Optional[str] = None,
) -> int:
    """Insert a new campaign in 'draft' state. Returns campaign id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO outreach_campaigns (base_id, table_id, goal, mapping_id, pitch_page_url, pitch_page_label)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            base_id, table_id, goal, mapping_id, pitch_page_url, pitch_page_label,
        )
    campaign_id = row["id"]
    logger.info(f"Created campaign {campaign_id} for {base_id}/{table_id} mapping={mapping_id}")
    return campaign_id


# Total real emails sent for a campaign = SUM of batch job send counts, excluding
# test-mode jobs. This counts every delivery (3 sends to one person = 3), unlike
# sent_count which counts distinct people reached.
_EMAILS_SENT_SUBQUERY = """
    LEFT JOIN (
        SELECT campaign_id, COALESCE(SUM(sent), 0) AS emails_sent
        FROM batch_send_jobs
        WHERE test_recipient IS NULL
        GROUP BY campaign_id
    ) j ON j.campaign_id = oc.id
"""


async def get_campaign(campaign_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT oc.*, COALESCE(j.emails_sent, 0) AS emails_sent
            FROM outreach_campaigns oc
            {_EMAILS_SENT_SUBQUERY}
            WHERE oc.id=$1
            """,
            campaign_id,
        )
    return _campaign_row(row) if row else None


async def list_campaigns(base_id: str, table_id: str, limit: int = 20) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT oc.*, COALESCE(j.emails_sent, 0) AS emails_sent
            FROM outreach_campaigns oc
            {_EMAILS_SENT_SUBQUERY}
            WHERE oc.base_id=$1 AND oc.table_id=$2
            ORDER BY oc.created_at DESC LIMIT $3
            """,
            base_id, table_id, limit,
        )
    return [_campaign_row(r) for r in rows]


async def update_campaign_status(
    campaign_id: int,
    status: str,
    error: Optional[str] = None,
    **extra: Any,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE outreach_campaigns SET
                status       = $1,
                error        = COALESCE($2, error),
                updated_at   = now(),
                completed_at = CASE WHEN $1 IN ('completed', 'failed') THEN now() ELSE completed_at END
            WHERE id = $3
            """,
            status, error, campaign_id,
        )


async def set_campaign_tier_counts(
    campaign_id: int,
    tier_1: int,
    tier_2: int,
    tier_3: int,
) -> None:
    """Write the tier counts produced by the segmentation agent (called once)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE outreach_campaigns SET
                warm_intro_count   = $1,
                direct_count       = $2,
                reengagement_count = $3,
                updated_at         = now()
            WHERE id = $4
            """,
            tier_1, tier_2, tier_3, campaign_id,
        )


async def increment_campaign_counter(campaign_id: int, field: str) -> None:
    """Atomically increment sent_count or skipped_count by 1."""
    if field not in ("sent_count", "skipped_count"):
        raise ValueError(f"Invalid counter field: {field}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE outreach_campaigns SET {field} = {field} + 1, updated_at = now() WHERE id = $1",
            campaign_id,
        )


async def delete_campaign(campaign_id: int) -> bool:
    """Delete campaign and all its contacts (cascade). Returns True if deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM outreach_campaigns WHERE id=$1", campaign_id
        )
    return result == "DELETE 1"


async def save_tier_insights(
    campaign_id: int,
    tier_1_insight: str = '',
    tier_2_insight: str = '',
    tier_3_insight: str = '',
) -> None:
    """Store AI-generated audience insights for each tier (called once after segmentation)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE outreach_campaigns SET
                tier_1_insight = $1,
                tier_2_insight = $2,
                tier_3_insight = $3,
                updated_at     = now()
            WHERE id = $4
            """,
            tier_1_insight or None, tier_2_insight or None, tier_3_insight or None, campaign_id,
        )


def _campaign_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("created_at", "updated_at", "completed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    # Alias old column names to new tier names (avoids schema migration)
    d["tier_1_count"] = d.pop("warm_intro_count", 0) or 0
    d["tier_2_count"] = d.pop("direct_count", 0) or 0
    d["tier_3_count"] = d.pop("reengagement_count", 0) or 0
    return d


# ---------------------------------------------------------------------------
# Campaign Contacts
# ---------------------------------------------------------------------------

async def bulk_insert_campaign_contacts(campaign_id: int, contacts: list[dict[str, Any]]) -> int:
    """
    Insert segmented contacts in batches of 500.
    Each contact dict must have: airtable_record_id, tier, composite_score,
    score_breakdown (dict), ai_reasoning (str), warm_path_data (dict|None).
    queue_position is set to the contact's index within its tier.

    Returns the total number of rows inserted.
    """
    if not contacts:
        return 0

    pool = await get_pool()

    tier_counters: dict[str, int] = {}
    rows = []
    for c in contacts:
        tier = c["tier"]
        pos = tier_counters.get(tier, 0)
        tier_counters[tier] = pos + 1
        rows.append((
            campaign_id,
            c["airtable_record_id"],
            tier,
            float(c.get("composite_score", 0.0)),
            json.dumps(c.get("score_breakdown", {})),
            c.get("ai_reasoning"),
            json.dumps(c["warm_path_data"]) if c.get("warm_path_data") else None,
            json.dumps(c.get("contact_snapshot", {})),
            pos,
        ))

    BATCH = 500
    inserted = 0
    async with pool.acquire() as conn:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i : i + BATCH]
            await conn.executemany(
                """
                INSERT INTO campaign_contacts
                    (campaign_id, airtable_record_id, tier, composite_score,
                     score_breakdown, ai_reasoning, warm_path_data, contact_snapshot, queue_position)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8::jsonb, $9)
                ON CONFLICT (campaign_id, airtable_record_id) DO NOTHING
                """,
                chunk,
                timeout=120,
            )
            inserted += len(chunk)

    logger.info(f"Campaign {campaign_id}: inserted {inserted} contacts ({len(contacts)} total)")
    return inserted


async def count_queue(campaign_id: int, tier: str, include_later: bool = True) -> int:
    """Return total contacts for a tier (all statuses — queue shows full history)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) FROM campaign_contacts WHERE campaign_id=$1 AND tier=$2",
            campaign_id, tier,
        )
    return int(row[0]) if row else 0


async def get_queue(
    campaign_id: int,
    tier: str,
    include_later: bool = True,
    offset: int = 0,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """
    Return all contacts for a tier ordered by queue_position.
    All statuses included — sent/skipped shown with reduced opacity in the sidebar.
    offset/limit for pagination; limit=0 returns all.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if limit > 0:
            rows = await conn.fetch(
                """
                SELECT * FROM campaign_contacts
                WHERE campaign_id = $1
                  AND tier = $2
                ORDER BY queue_position ASC
                OFFSET $3 LIMIT $4
                """,
                campaign_id, tier, offset, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM campaign_contacts
                WHERE campaign_id = $1
                  AND tier = $2
                ORDER BY queue_position ASC
                """,
                campaign_id, tier,
            )
    return [_contact_row(r) for r in rows]


async def get_campaign_contact(contact_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM campaign_contacts WHERE id=$1", contact_id
        )
    return _contact_row(row) if row else None


async def get_contact_by_record(
    campaign_id: int, airtable_record_id: str
) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM campaign_contacts
            WHERE campaign_id=$1 AND airtable_record_id=$2
            """,
            campaign_id, airtable_record_id,
        )
    return _contact_row(row) if row else None


async def send_contact(contact_id: int, sent_draft: str) -> None:
    """Mark a contact as sent and persist the exact draft that was sent."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE campaign_contacts SET
                status     = 'sent',
                sent_draft = $1,
                sent_at    = now(),
                updated_at = now()
            WHERE id = $2
            """,
            sent_draft, contact_id,
        )


async def skip_contact(contact_id: int) -> None:
    """Mark a contact as skipped (stays in campaign, just flagged)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE campaign_contacts SET status='skipped', updated_at=now() WHERE id=$1",
            contact_id,
        )


async def park_contact_later(contact_id: int, campaign_id: int, tier: str) -> None:
    """
    Push a contact to the bottom of its tier queue (Later action).
    Uses MAX(queue_position) + 1 so the contact is always last — no full
    reorder needed, no gaps introduced in existing positions.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE campaign_contacts SET
                status         = 'later',
                queue_position = (
                    SELECT COALESCE(MAX(queue_position), -1) + 1
                    FROM campaign_contacts
                    WHERE campaign_id = $2 AND tier = $3
                ),
                updated_at     = now()
            WHERE id = $1
            """,
            contact_id, campaign_id, tier,
        )


async def move_contact_tier(contact_id: int, new_tier: str) -> None:
    """Fundraiser manually reassigns a contact to a different tier."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE campaign_contacts SET
                tier_override  = $1,
                tier           = $1,
                status         = 'pending',
                queue_position = (
                    SELECT COALESCE(MAX(queue_position), -1) + 1
                    FROM campaign_contacts cc2
                    WHERE cc2.campaign_id = campaign_contacts.campaign_id
                      AND cc2.tier = $1
                ),
                updated_at     = now()
            WHERE id = $2
            """,
            new_tier, contact_id,
        )


async def get_campaign_stats(campaign_id: int) -> dict[str, Any]:
    """
    Return per-tier contact counts + template status + latest batch job.
    Used for the tier cards and progress indicators.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        contact_rows = await conn.fetch(
            """
            SELECT tier, status, COUNT(*) AS cnt
            FROM campaign_contacts
            WHERE campaign_id = $1
            GROUP BY tier, status
            """,
            campaign_id,
        )
        template_rows = await conn.fetch(
            """
            SELECT tier,
                CASE WHEN MAX(CASE WHEN status='approved' THEN 1 ELSE 0 END) = 1 THEN 'approved'
                     WHEN COUNT(*) > 0 THEN 'draft'
                     ELSE NULL
                END AS template_status
            FROM campaign_templates WHERE campaign_id = $1
            GROUP BY tier
            """,
            campaign_id,
        )
        job_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (tier)
                tier, id, status, total, sent, failed, scope, created_at
            FROM batch_send_jobs
            WHERE campaign_id = $1
            ORDER BY tier, created_at DESC
            """,
            campaign_id,
        )

    stats: dict[str, dict] = {}

    for r in contact_rows:
        tier = r["tier"]
        if tier not in stats:
            stats[tier] = {"pending": 0, "sent": 0, "skipped": 0, "later": 0, "total": 0,
                           "template_status": None, "latest_job": None}
        stats[tier][r["status"]] = r["cnt"]
        stats[tier]["total"] += r["cnt"]

    for r in template_rows:
        tier = r["tier"]
        if tier not in stats:
            stats[tier] = {"pending": 0, "sent": 0, "skipped": 0, "later": 0, "total": 0,
                           "template_status": None, "latest_job": None}
        stats[tier]["template_status"] = r["template_status"]

    for r in job_rows:
        tier = r["tier"]
        if tier not in stats:
            stats[tier] = {"pending": 0, "sent": 0, "skipped": 0, "later": 0, "total": 0,
                           "template_status": None, "latest_job": None}
        stats[tier]["latest_job"] = {
            "id": r["id"],
            "status": r["status"],
            "total": r["total"],
            "sent": r["sent"],
            "failed": r["failed"],
            "scope": r["scope"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }

    return stats


async def sample_queue(campaign_id: int, tier: str, count: int = 5) -> list[dict[str, Any]]:
    """Return up to `count` random contacts from a tier for preview (any status)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM campaign_contacts
            WHERE campaign_id = $1
              AND tier = $2
            ORDER BY RANDOM()
            LIMIT $3
            """,
            campaign_id, tier, count,
        )
    return [_contact_row(r) for r in rows]


async def get_prior_sends(airtable_record_id: str, limit: int = 3) -> list[dict[str, Any]]:
    """
    Return the last N sent drafts for a contact across all campaigns.
    Used to give the draft agent conversation history context.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.sent_draft, cc.sent_at, oc.goal, cc.tier
            FROM campaign_contacts cc
            JOIN outreach_campaigns oc ON oc.id = cc.campaign_id
            WHERE cc.airtable_record_id = $1
              AND cc.status = 'sent'
            ORDER BY cc.sent_at DESC LIMIT $2
            """,
            airtable_record_id, limit,
        )
    return [
        {
            "sent_draft": r["sent_draft"],
            "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
            "campaign_goal": r["goal"],
            "tier": r["tier"],
        }
        for r in rows
    ]


def _contact_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("score_breakdown", "warm_path_data", "contact_snapshot"):
        if d.get(k) is not None and isinstance(d[k], str):
            d[k] = json.loads(d[k])
    for k in ("sent_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Campaign Templates
# ---------------------------------------------------------------------------

async def get_campaign_template(campaign_id: int, tier: str) -> Optional[dict[str, Any]]:
    """Return the most recent template for a campaign tier, or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM campaign_templates WHERE campaign_id=$1 AND tier=$2 ORDER BY updated_at DESC LIMIT 1",
            campaign_id, tier,
        )
    return _template_row(row) if row else None


async def get_campaign_template_by_id(template_id: int) -> Optional[dict[str, Any]]:
    """Return a specific template by its ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM campaign_templates WHERE id=$1", template_id)
    return _template_row(row) if row else None


async def create_campaign_template(campaign_id: int, tier: str) -> dict[str, Any]:
    """Create a fresh blank template record. Returns the new row with its ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO campaign_templates (campaign_id, tier, subject, body, variables)
            VALUES ($1, $2, '', '', '[]'::jsonb)
            RETURNING *
            """,
            campaign_id, tier,
        )
    return _template_row(row)


async def update_campaign_template_by_id(
    template_id: int,
    subject: str = '',
    body: str = '',
    variables: Optional[list] = None,
    tier_summary: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Update a specific template record by ID. Returns the updated row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE campaign_templates
            SET subject=$2, body=$3, variables=$4::jsonb,
                tier_summary=COALESCE($5, tier_summary), updated_at=now()
            WHERE id=$1
            RETURNING *
            """,
            template_id, subject, body,
            json.dumps(variables or []), tier_summary,
        )
    return _template_row(row) if row else None


async def upsert_campaign_template(
    campaign_id: int,
    tier: str,
    subject: str = '',
    body: str = '',
    variables: Optional[list] = None,
    tier_summary: Optional[str] = None,
) -> dict[str, Any]:
    """Insert a new template row. Returns the full template row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO campaign_templates
                (campaign_id, tier, subject, body, variables, tier_summary)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            RETURNING *
            """,
            campaign_id, tier, subject, body,
            json.dumps(variables or []), tier_summary,
        )
    return _template_row(row)


async def approve_campaign_template(campaign_id: int, tier: str) -> bool:
    """Lock a template as approved. Returns True if updated."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE campaign_templates SET status='approved', updated_at=now() WHERE campaign_id=$1 AND tier=$2",
            campaign_id, tier,
        )
    return result == "UPDATE 1"


def _template_row(row) -> dict[str, Any]:
    d = dict(row)
    if d.get('variables') is not None and isinstance(d['variables'], str):
        d['variables'] = json.loads(d['variables'])
    for k in ('created_at', 'updated_at'):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Batch Send Jobs
# ---------------------------------------------------------------------------

async def count_scope_contacts(campaign_id: int, tier: str, scope: str) -> int:
    """Count how many contacts a batch send scope would target."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if scope == "everyone":
            row = await conn.fetchrow(
                "SELECT COUNT(*) FROM campaign_contacts WHERE campaign_id=$1 AND tier=$2",
                campaign_id, tier,
            )
        else:  # unsent — pending + later
            row = await conn.fetchrow(
                """SELECT COUNT(*) FROM campaign_contacts
                   WHERE campaign_id=$1 AND tier=$2 AND status IN ('pending', 'later')""",
                campaign_id, tier,
            )
    return int(row[0])


async def create_batch_send_job(
    campaign_id: int,
    template_id: int,
    tier: str,
    total: int,
    scope: str = "unsent",
    sender_emails: Optional[list] = None,
    test_recipient: Optional[str] = None,
) -> int:
    """Create a new batch send job. Returns job id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO batch_send_jobs (campaign_id, template_id, tier, total, scope, sender_emails, test_recipient)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING id
            """,
            campaign_id, template_id, tier, total, scope,
            json.dumps(sender_emails or []),
            test_recipient,
        )
    return row['id']


async def list_batch_send_jobs(
    campaign_id: int,
    tier: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List all batch send jobs for a campaign, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if tier:
            rows = await conn.fetch(
                "SELECT * FROM batch_send_jobs WHERE campaign_id=$1 AND tier=$2 ORDER BY created_at DESC",
                campaign_id, tier,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM batch_send_jobs WHERE campaign_id=$1 ORDER BY created_at DESC",
                campaign_id,
            )
    return [_batch_send_row(r) for r in rows]


async def get_batch_send_job(job_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM batch_send_jobs WHERE id=$1", job_id)
    return _batch_send_row(row) if row else None


async def get_running_batch_send_jobs() -> list[dict[str, Any]]:
    """Jobs left mid-flight (running/pending) — used by startup recovery to resume
    sends stranded by a deploy, crash, or free-tier sleep."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM batch_send_jobs WHERE status IN ('running','pending') ORDER BY created_at"
        )
    return [_batch_send_row(r) for r in rows]


async def estimate_quota_reset_for_job(job_id: int) -> Optional[str]:
    """
    Estimate when Gmail's rolling 24h send-quota will free up enough to resume
    the given batch job.

    Mechanism: Gmail's daily limit is rolling-window — each sent message ages
    out of the quota 24h after it was sent. So the next "slot" opens up 24h
    after the *earliest* still-counted send. We compute that earliest by
    looking at campaign_contacts.sent_at for the job's campaign + tier within
    the past 24h.

    Caveat: campaign_contacts.sent_at isn't tagged with which sender account
    sent it, so for multi-sender (round-robin) jobs this is conservative —
    a per-sender estimate could open up slightly earlier. For single-sender
    jobs (the common case) it's accurate.

    Returns an ISO timestamp string, or None if there are no sends in the
    last 24h to compute from.
    """
    from datetime import timedelta
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Read the job's campaign + tier so we know what to look at.
        job_row = await conn.fetchrow(
            "SELECT campaign_id, tier FROM batch_send_jobs WHERE id=$1",
            job_id,
        )
        if not job_row:
            return None
        earliest_row = await conn.fetchrow(
            """
            SELECT MIN(sent_at) AS earliest
            FROM campaign_contacts
            WHERE campaign_id = $1
              AND tier        = $2
              AND status      = 'sent'
              AND sent_at     > now() - interval '24 hours'
            """,
            job_row["campaign_id"], job_row["tier"],
        )
    earliest = earliest_row["earliest"] if earliest_row else None
    if not earliest:
        return None
    return (earliest + timedelta(hours=24)).isoformat()


async def update_batch_send_job(job_id: int, **fields) -> None:
    if not fields:
        return
    pool = await get_pool()
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE batch_send_jobs SET {sets} WHERE id=$1",
            job_id, *fields.values(),
        )


async def list_all_batch_send_jobs_for_table(base_id: str, table_id: str) -> list[dict[str, Any]]:
    """All batch email jobs for campaigns in a base/table, newest first, with campaign goal."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT bsj.*, oc.goal AS campaign_goal
            FROM batch_send_jobs bsj
            JOIN outreach_campaigns oc ON oc.id = bsj.campaign_id
            WHERE oc.base_id = $1 AND oc.table_id = $2
            ORDER BY bsj.created_at DESC
            """,
            base_id, table_id,
        )
    return [_batch_send_row(r) for r in rows]


async def cancel_or_delete_batch_send_job(job_id: int) -> None:
    """Hard-delete a batch send job regardless of status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM batch_send_jobs WHERE id=$1", job_id)


async def cancel_batch_send_job(job_id: int) -> bool:
    """
    Gracefully cancel a running, pending, or paused job.
    The runner checks status at each chunk boundary and exits on 'cancelled'.
    Returns True if the row was updated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE batch_send_jobs SET status='cancelled' WHERE id=$1 AND status IN ('pending','running','paused')",
            job_id,
        )
    return result != "UPDATE 0"


async def pause_batch_send_job(job_id: int) -> bool:
    """
    Signal the runner to pause at the next chunk boundary.
    Only valid for running or pending jobs. Returns True if updated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE batch_send_jobs SET status='paused' WHERE id=$1 AND status IN ('running','pending')",
            job_id,
        )
    return result != "UPDATE 0"


async def resume_batch_send_job(job_id: int) -> bool:
    """
    Mark a paused job as running so a fresh runner task can pick up remaining contacts.
    Returns True if the row was updated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE batch_send_jobs SET status='running' WHERE id=$1 AND status='paused'",
            job_id,
        )
    return result != "UPDATE 0"


async def get_pending_contacts_for_job(
    campaign_id: int,
    tier: str,
    scope: str = "unsent",
) -> list[dict[str, Any]]:
    """
    Return contacts targeted by a batch send job, ordered by queue_position.
    scope='unsent'   → pending + later contacts only
    scope='everyone' → all contacts in the tier

    Suppression: contacts whose email is on the active email_suppressions list
    are silently filtered out — same guard as enroll_tier in sequence_repo,
    applied per-batch instead of per-sequence.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if scope == "everyone":
            rows = await conn.fetch(
                """
                SELECT * FROM campaign_contacts
                WHERE campaign_id=$1 AND tier=$2
                  AND LOWER(contact_snapshot->>'email') NOT IN (
                      SELECT email FROM email_suppressions
                      WHERE retry_after IS NULL OR retry_after < now()
                  )
                ORDER BY queue_position
                """,
                campaign_id, tier,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM campaign_contacts
                WHERE campaign_id=$1 AND tier=$2 AND status IN ('pending','later')
                  AND LOWER(contact_snapshot->>'email') NOT IN (
                      SELECT email FROM email_suppressions
                      WHERE retry_after IS NULL OR retry_after < now()
                  )
                ORDER BY queue_position
                """,
                campaign_id, tier,
            )
    return [_contact_row(r) for r in rows]


async def bulk_mark_sent_contacts(results: list) -> None:
    """
    Mark sent contacts in campaign_contacts.
    Only processes entries with status='sent'; failed contacts stay 'pending'
    so they are eligible for retry in a subsequent job.

    results: list of ContactSendResult(contact_id, status, rendered_body)
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    pool = await get_pool()
    sent = [(r.contact_id, r.rendered_body, now) for r in results if r.status == "sent"]
    if not sent:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            UPDATE campaign_contacts
            SET status='sent', sent_draft=$2, sent_at=$3, updated_at=$3
            WHERE id=$1
            """,
            sent,
        )


async def sync_campaign_sent_count(campaign_id: int) -> None:
    """Recompute outreach_campaigns.sent_count from campaign_contacts so the
    campaign card always shows the correct sent total without a manual refresh."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE outreach_campaigns
            SET sent_count = (
                SELECT COUNT(*) FROM campaign_contacts
                WHERE campaign_id = $1 AND status = 'sent'
            ), updated_at = now()
            WHERE id = $1
            """,
            campaign_id,
        )


def _batch_send_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ('created_at', 'started_at', 'completed_at', 'retry_after'):
        if d.get(k):
            d[k] = d[k].isoformat()
    if d.get('sender_emails') is not None and isinstance(d['sender_emails'], str):
        d['sender_emails'] = json.loads(d['sender_emails'])
    return d


# ---------------------------------------------------------------------------
# Campaign Files
# ---------------------------------------------------------------------------

async def create_campaign_file(
    campaign_id: int,
    filename: str,
    file_type: str,
    parsed_content: Optional[str] = None,
    row_count: Optional[int] = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO campaign_files (campaign_id, filename, file_type, parsed_content, row_count)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            campaign_id, filename, file_type, parsed_content, row_count,
        )
    return row['id']


async def get_campaign_files(campaign_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, campaign_id, filename, file_type, row_count, created_at FROM campaign_files WHERE campaign_id=$1 ORDER BY created_at DESC",
            campaign_id,
        )
    return [_file_row(r) for r in rows]


async def get_campaign_source_material(campaign_id: int, max_chars: int = 2500) -> str:
    """
    Concatenated parsed text of any decks/briefs attached to the campaign, trimmed
    to max_chars. Returns '' when no files are attached — generation is unaffected.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT filename, parsed_content
            FROM campaign_files
            WHERE campaign_id=$1 AND parsed_content IS NOT NULL AND parsed_content <> ''
            ORDER BY created_at ASC
            """,
            campaign_id,
        )
    if not rows:
        return ''
    parts: list[str] = []
    budget = max_chars
    for r in rows:
        if budget <= 0:
            break
        snippet = (r["parsed_content"] or "")[:budget].strip()
        if snippet:
            parts.append(f"[{r['filename']}]\n{snippet}")
            budget -= len(snippet)
    return "\n\n".join(parts)


async def delete_campaign_file(file_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM campaign_files WHERE id=$1", file_id)
    return result == "DELETE 1"


def _file_row(row) -> dict[str, Any]:
    d = dict(row)
    if d.get('created_at'):
        d['created_at'] = d['created_at'].isoformat()
    return d
