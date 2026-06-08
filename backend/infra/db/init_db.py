"""
Database initialisation script - creates tables if they don't exist.
Safe to run multiple times (idempotent).

Usage:
    python -m backend.db.init_db
"""
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import Config
from backend.infra.db.client import get_pool, close_pool

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DDL = """
-- Field mappings: multiple named mappings per (base, table)
CREATE TABLE IF NOT EXISTS field_mappings (
    id          SERIAL PRIMARY KEY,
    base_id     TEXT NOT NULL,
    table_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    mappings    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enrichment jobs: one row per user-initiated run
CREATE TABLE IF NOT EXISTS enrichment_jobs (
    id              SERIAL PRIMARY KEY,
    base_id         TEXT NOT NULL,
    table_id        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    field_mapping   JSONB NOT NULL,
    batch_size      INT NOT NULL DEFAULT 100,
    total_records   INT,
    total_batches   INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Prevent two active jobs on the same table at once
CREATE UNIQUE INDEX IF NOT EXISTS one_active_job
    ON enrichment_jobs (base_id, table_id)
    WHERE status IN ('pending', 'running', 'paused');

-- Enrichment batches: one row per chunk of records within a job
CREATE TABLE IF NOT EXISTS enrichment_batches (
    id              SERIAL PRIMARY KEY,
    job_id          INT NOT NULL REFERENCES enrichment_jobs(id) ON DELETE CASCADE,
    batch_number    INT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    record_ids      JSONB NOT NULL,
    csv_path        TEXT,
    total           INT NOT NULL,
    processed       INT NOT NULL DEFAULT 0,
    hits            INT NOT NULL DEFAULT 0,
    misses          INT NOT NULL DEFAULT 0,
    failed          INT NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    UNIQUE (job_id, batch_number)
);

-- Warm path runs: one row per computation run (auto-triggered or manual)
CREATE TABLE IF NOT EXISTS warm_path_runs (
    id                SERIAL PRIMARY KEY,
    base_id           TEXT NOT NULL,
    table_id          TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    triggered_by      TEXT NOT NULL DEFAULT 'auto',
    enrichment_job_id INT REFERENCES enrichment_jobs(id) ON DELETE SET NULL,
    contacts_loaded   INT,
    targets_found     INT,
    paths_found       INT,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

-- Contact embeddings: one row per Airtable record, upserted on re-index
-- Requires pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS contact_embeddings (
    id                  SERIAL PRIMARY KEY,
    airtable_record_id  TEXT NOT NULL,
    base_id             TEXT NOT NULL,
    table_id            TEXT NOT NULL,
    embedding           vector(1536),
    content_hash        TEXT NOT NULL,
    embedded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (airtable_record_id)
);

CREATE INDEX IF NOT EXISTS contact_embeddings_base_table_idx
    ON contact_embeddings (base_id, table_id);

-- Embedding runs: one row per indexing run (auto or manual)
CREATE TABLE IF NOT EXISTS embedding_runs (
    id                SERIAL PRIMARY KEY,
    base_id           TEXT NOT NULL,
    table_id          TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    triggered_by      TEXT NOT NULL DEFAULT 'auto',
    enrichment_job_id INT REFERENCES enrichment_jobs(id) ON DELETE SET NULL,
    total_contacts    INT,
    indexed           INT,
    skipped           INT,
    failed            INT,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

-- ── Outreach Campaigns ────────────────────────────────────────────────────
-- One row per fundraising campaign. Tracks goal, segmentation state, and
-- denormalised progress counters so tier cards never need a COUNT(*) query.
--
-- Status lifecycle:
--   draft → segmenting → ready → in_progress → completed | failed
CREATE TABLE IF NOT EXISTS outreach_campaigns (
    id                  SERIAL PRIMARY KEY,
    base_id             TEXT NOT NULL,
    table_id            TEXT NOT NULL,
    goal                TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'segmenting', 'ready', 'in_progress', 'completed', 'failed')),
    error               TEXT,

    -- Denormalised tier counts — written once on segmentation complete, never
    -- incremented in a hot loop. Avoids expensive COUNT(*) on every page load.
    warm_intro_count    INT NOT NULL DEFAULT 0,
    direct_count        INT NOT NULL DEFAULT 0,
    reengagement_count  INT NOT NULL DEFAULT 0,

    -- Tier audience insights — generated post-segmentation, shown on tier cards
    tier_1_insight      TEXT,
    tier_2_insight      TEXT,
    tier_3_insight      TEXT,

    -- Progress counters — incremented atomically on send / skip
    sent_count          INT NOT NULL DEFAULT 0,
    skipped_count       INT NOT NULL DEFAULT 0,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ
);

-- Primary list path: campaigns for a base/table ordered newest-first
CREATE INDEX IF NOT EXISTS outreach_campaigns_base_table_idx
    ON outreach_campaigns (base_id, table_id, created_at DESC);

-- Prevent two concurrent segmentation runs on the same table
CREATE UNIQUE INDEX IF NOT EXISTS one_segmenting_per_table
    ON outreach_campaigns (base_id, table_id)
    WHERE status = 'segmenting';

-- Dedup runs: health-check that finds and removes duplicate records before enrichment
-- Runs async so the UI can poll for status even if the user navigates away.
CREATE TABLE IF NOT EXISTS dedup_runs (
    id                SERIAL PRIMARY KEY,
    base_id           TEXT NOT NULL,
    table_id          TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    triggered_by      TEXT NOT NULL DEFAULT 'auto',
    enrichment_job_id INT REFERENCES enrichment_jobs(id) ON DELETE SET NULL,
    records_checked   INT,
    groups_found      INT,
    records_deleted   INT,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS dedup_runs_base_table_idx
    ON dedup_runs (base_id, table_id, created_at DESC);

-- ── Campaign Contacts ──────────────────────────────────────────────────────
-- One row per (campaign, contact). Bulk-inserted when segmentation completes
-- (~3 k rows max); updated individually as the fundraiser works the queue.
CREATE TABLE IF NOT EXISTS campaign_contacts (
    id                  SERIAL PRIMARY KEY,
    campaign_id         INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    airtable_record_id  TEXT NOT NULL,

    -- Tier from the segmentation agent; override written if fundraiser moves
    -- the contact to a different tier before sending
    tier                TEXT NOT NULL
                        CHECK (tier IN ('tier_1', 'tier_2', 'tier_3')),
    tier_override       TEXT
                        CHECK (tier_override IS NULL OR
                               tier_override IN ('tier_1', 'tier_2', 'tier_3')),

    -- Composite score [0, 1] and per-component breakdown stored for auditability
    -- and for Phase-3 outlier surfacing without re-running the agent
    composite_score     FLOAT NOT NULL DEFAULT 0.0
                        CHECK (composite_score >= 0.0 AND composite_score <= 1.0),
    score_breakdown     JSONB NOT NULL DEFAULT '{}',

    -- Agent reasoning shown in the context panel (plain text, one paragraph)
    ai_reasoning        TEXT,

    -- Full warm-path details for warm_intro tier
    -- Shape: {"path": ["You", "Sarah Chen", "David Kim"], "score": 0.8, "connector": "Sarah Chen"}
    warm_path_data      JSONB,

    -- Queue state
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'sent', 'skipped', 'later')),

    -- Ordering within (campaign, tier). 'Later' action bumps to MAX + 1.
    queue_position      INT NOT NULL DEFAULT 0,

    -- Saved only on send — draft lives in memory until the fundraiser clicks Send
    sent_at             TIMESTAMPTZ,
    sent_draft          TEXT,

    -- DB-level integrity: if status = sent, both fields must be present
    CONSTRAINT sent_fields_required
        CHECK (status != 'sent' OR (sent_at IS NOT NULL AND sent_draft IS NOT NULL)),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One contact per campaign — prevents duplicate segmentation results
    UNIQUE (campaign_id, airtable_record_id)
);

-- Primary queue read: pending + later contacts for a campaign tier, ordered.
-- Partial index keeps this small as sent/skipped rows accumulate over time.
CREATE INDEX IF NOT EXISTS campaign_contacts_queue_idx
    ON campaign_contacts (campaign_id, tier, queue_position)
    WHERE status IN ('pending', 'later');

-- Campaign progress stats (sent / skipped counts per tier)
CREATE INDEX IF NOT EXISTS campaign_contacts_status_idx
    ON campaign_contacts (campaign_id, status);

-- Phase 3: surface lowest-scored pending contacts first for outlier review
CREATE INDEX IF NOT EXISTS campaign_contacts_score_idx
    ON campaign_contacts (campaign_id, composite_score DESC)
    WHERE status = 'pending';

-- Cross-campaign contact history: has this person been reached before?
-- Used in Phase 4 to pull prior sends as draft context.
CREATE INDEX IF NOT EXISTS campaign_contacts_record_idx
    ON campaign_contacts (airtable_record_id);

-- ── Batch Email Tables ────────────────────────────────────────────────────

-- One per (campaign, tier) — created lazily when fundraiser enters batch mode.
-- Template is editable until approved; locked once approved.
CREATE TABLE IF NOT EXISTS campaign_templates (
    id              SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    tier            TEXT NOT NULL CHECK (tier IN ('tier_1', 'tier_2', 'tier_3')),
    subject         TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL DEFAULT '',
    variables       JSONB NOT NULL DEFAULT '[]',
    tier_summary    TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, tier)
);

-- Batch send jobs — one row per "send this template to all pending tier contacts" run.
CREATE TABLE IF NOT EXISTS batch_send_jobs (
    id              SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    template_id     INT NOT NULL REFERENCES campaign_templates(id),
    tier            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    total           INT NOT NULL DEFAULT 0,
    sent            INT NOT NULL DEFAULT 0,
    failed          INT NOT NULL DEFAULT 0,
    error           TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Uploaded files (CSV/PDF/DOCX) attached to a campaign for copilot context.
CREATE TABLE IF NOT EXISTS campaign_files (
    id              SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    file_type       TEXT NOT NULL CHECK (file_type IN ('csv', 'xlsx', 'pdf', 'docx', 'txt')),
    parsed_content  TEXT,
    row_count       INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Gmail OAuth tokens — one row per connected account.
CREATE TABLE IF NOT EXISTS gmail_tokens (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT,
    token_expiry    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Cadence (multi-touch sequences) ────────────────────────────────────────
-- A sequence is a timed series of emails for a (campaign, tier). Each step is a
-- template + a delay. Contacts are enrolled and advanced by the cadence scheduler.

CREATE TABLE IF NOT EXISTS sequences (
    id              SERIAL PRIMARY KEY,
    campaign_id     INT NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    tier            TEXT NOT NULL CHECK (tier IN ('tier_1', 'tier_2', 'tier_3')),
    name            TEXT NOT NULL DEFAULT 'Sequence',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'paused', 'completed')),
    sender_emails   JSONB NOT NULL DEFAULT '[]',
    test_recipient  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sequences_campaign_idx ON sequences (campaign_id, tier);

-- One row per step. delay_days is the wait AFTER the previous step (step 1 = 0).
CREATE TABLE IF NOT EXISTS sequence_steps (
    id              SERIAL PRIMARY KEY,
    sequence_id     INT NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
    step_number     INT NOT NULL,
    delay_days      INT NOT NULL DEFAULT 0,
    template_id     INT NOT NULL REFERENCES campaign_templates(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sequence_id, step_number)
);

-- One row per enrolled contact. The scheduler reads rows where status='active'
-- AND next_send_at <= now(), sends the current step, then advances.
CREATE TABLE IF NOT EXISTS sequence_enrollments (
    id                  SERIAL PRIMARY KEY,
    sequence_id         INT NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
    campaign_contact_id INT NOT NULL REFERENCES campaign_contacts(id) ON DELETE CASCADE,
    current_step        INT NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'replied', 'completed', 'stopped', 'bounced')),
    next_send_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Gmail thread/message ids of the last send (Phase 2 reply detection)
    last_thread_id      TEXT,
    last_message_id     TEXT,
    sent_count          INT NOT NULL DEFAULT 0,
    enrolled_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sequence_id, campaign_contact_id)
);

-- The scheduler's hot query: due, active enrollments.
CREATE INDEX IF NOT EXISTS sequence_enrollments_due_idx
    ON sequence_enrollments (next_send_at)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS sequence_enrollments_seq_idx
    ON sequence_enrollments (sequence_id, status);

-- ── Migrations: columns added after initial deploy (idempotent) ────────────
ALTER TABLE enrichment_batches  ADD COLUMN IF NOT EXISTS hits             INT  NOT NULL DEFAULT 0;
ALTER TABLE enrichment_batches  ADD COLUMN IF NOT EXISTS misses           INT  NOT NULL DEFAULT 0;
-- failures: durable per-record failure reasons [{record_id, linkedin_url, error}],
-- written at batch completion so the "view failures" panel survives restarts (CSV is ephemeral on Render).
ALTER TABLE enrichment_batches  ADD COLUMN IF NOT EXISTS failures         JSONB NOT NULL DEFAULT '[]';
ALTER TABLE campaign_contacts   ADD COLUMN IF NOT EXISTS contact_snapshot JSONB NOT NULL DEFAULT '{}';
ALTER TABLE outreach_campaigns  ADD COLUMN IF NOT EXISTS mapping_id       INT  REFERENCES field_mappings(id);
ALTER TABLE batch_send_jobs     ADD COLUMN IF NOT EXISTS scope            TEXT NOT NULL DEFAULT 'unsent';
ALTER TABLE campaign_templates  DROP CONSTRAINT IF EXISTS campaign_templates_campaign_id_tier_key;
ALTER TABLE outreach_campaigns  ADD COLUMN IF NOT EXISTS tier_1_insight TEXT;
ALTER TABLE outreach_campaigns  ADD COLUMN IF NOT EXISTS tier_2_insight TEXT;
ALTER TABLE outreach_campaigns  ADD COLUMN IF NOT EXISTS tier_3_insight TEXT;
-- sender_emails: which connected accounts to use for this job (round-robin if multiple)
ALTER TABLE batch_send_jobs     ADD COLUMN IF NOT EXISTS sender_emails    JSONB NOT NULL DEFAULT '[]';
-- paused status: allow runner to stop cleanly at a chunk boundary and be resumed
ALTER TABLE batch_send_jobs     DROP CONSTRAINT IF EXISTS batch_send_jobs_status_check;
ALTER TABLE batch_send_jobs     ADD CONSTRAINT batch_send_jobs_status_check
    CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled'));
-- test_recipient: when set, all emails in this job are redirected here with [TEST → Name] subject prefix
ALTER TABLE batch_send_jobs     ADD COLUMN IF NOT EXISTS test_recipient TEXT;
-- pause_reason: set to 'rate_limited' on auto-pause, null on manual pause/resume
ALTER TABLE enrichment_jobs     ADD COLUMN IF NOT EXISTS pause_reason TEXT;
-- Same idea for batch sends — distinguishes auto-pause from manual pause so
-- the UI only shows the "Gmail hit its quota" banner when that's actually true.
ALTER TABLE batch_send_jobs     ADD COLUMN IF NOT EXISTS pause_reason TEXT;
-- retry_after: ISO timestamp hint from Gmail Retry-After header; shown in UI banner
ALTER TABLE batch_send_jobs     ADD COLUMN IF NOT EXISTS retry_after  TIMESTAMPTZ;
-- last_reply_check_at: rotates the reply poller fairly across all enrollments
-- (order by this, oldest first) so large active sets are all covered, not a stuck window.
ALTER TABLE sequence_enrollments ADD COLUMN IF NOT EXISTS last_reply_check_at TIMESTAMPTZ;

-- ── Bounce auto-detection (Phase A) ──────────────────────────────────────────
--
-- Canonical dead-list keyed by email address. Read by enroll_tier (sequences)
-- and the batch contact-selection query on every send to suppress contacts
-- we already know are dead. retry_after lets soft bounces re-enter the pool
-- after a backoff; hard bounces leave it NULL forever.
CREATE TABLE IF NOT EXISTS email_suppressions (
    id                SERIAL PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE,
    reason            TEXT NOT NULL
                      CHECK (reason IN ('hard_bounce', 'soft_bounce', 'mx_invalid',
                                        'sync_rejected', 'unsubscribed', 'manual')),
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    retry_after       TIMESTAMPTZ,
    last_smtp_status  TEXT,
    last_reason_text  TEXT
);
-- Active (un-retryable) suppression index — what the send-side filter actually queries.
CREATE INDEX IF NOT EXISTS email_suppressions_active_idx
    ON email_suppressions (email)
    WHERE retry_after IS NULL;

-- Audit log of every detected bounce event. Multiple rows per email are normal
-- (a soft bounce, then a hard bounce, then a re-add). dsn_message_id UNIQUE
-- gives the DSN poller idempotency on restart.
CREATE TABLE IF NOT EXISTS email_bounces (
    id                       SERIAL PRIMARY KEY,
    email                    TEXT NOT NULL,
    source                   TEXT NOT NULL
                             CHECK (source IN ('sequence', 'batch', 'mx_preflight',
                                               'sync_error', 'dsn')),
    sequence_enrollment_id   INT REFERENCES sequence_enrollments(id) ON DELETE SET NULL,
    batch_job_id             INT REFERENCES batch_send_jobs(id) ON DELETE SET NULL,
    hard                     BOOLEAN NOT NULL,
    reason                   TEXT,
    smtp_status              TEXT,
    source_message_id        TEXT,
    dsn_message_id           TEXT UNIQUE,
    detected_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS email_bounces_email_idx       ON email_bounces (email);
CREATE INDEX IF NOT EXISTS email_bounces_sequence_idx    ON email_bounces (sequence_enrollment_id) WHERE sequence_enrollment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS email_bounces_batch_idx       ON email_bounces (batch_job_id)           WHERE batch_job_id           IS NOT NULL;

-- DSN scan cursor per Gmail account — Gmail history.list resumes from this id
-- so the poller processes only NEW inbox changes, not the whole inbox each tick.
ALTER TABLE gmail_tokens ADD COLUMN IF NOT EXISTS last_dsn_history_id TEXT;

-- ── Click engagement tracking (Phase B) ──────────────────────────────────────
--
-- Engagement events: a row per recipient action we can attribute to an
-- enrollment. Today it's clicks via the /r redirect endpoint; the pixel_hit
-- event_type is reserved so we can layer in delivery-confirmation pings on
-- the same table later without another migration.
CREATE TABLE IF NOT EXISTS email_events (
    id                       SERIAL PRIMARY KEY,
    sequence_enrollment_id   INT REFERENCES sequence_enrollments(id) ON DELETE SET NULL,
    batch_job_id             INT REFERENCES batch_send_jobs(id)      ON DELETE SET NULL,
    campaign_contact_id      INT REFERENCES campaign_contacts(id)    ON DELETE SET NULL,
    event_type               TEXT NOT NULL CHECK (event_type IN ('click', 'pixel_hit')),
    link_url                 TEXT,
    user_agent               TEXT,
    ip                       TEXT,
    occurred_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS email_events_sequence_idx
    ON email_events (sequence_enrollment_id)
    WHERE sequence_enrollment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS email_events_batch_idx
    ON email_events (batch_job_id)
    WHERE batch_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS email_events_contact_type_time_idx
    ON email_events (campaign_contact_id, event_type, occurred_at DESC);

-- Pitch page: an optional canonical URL per campaign. When set, the system
-- appends a tracked CTA to every email sent on that campaign (sequence OR
-- batch), so every recipient gets at least one signed, click-loggable link.
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS pitch_page_url   TEXT;
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS pitch_page_label TEXT;
"""


async def apply_migrations() -> None:
    """
    Apply the idempotent DDL block against the configured database.

    Safe to call from the FastAPI startup lifespan AND from the CLI: every
    statement uses IF NOT EXISTS / DROP IF EXISTS so reruns are no-ops.
    Does NOT manage the asyncpg pool lifecycle — callers that own the pool
    (the lifespan) keep it open after; the CLI closes it explicitly.

    Raises asyncpg errors so callers can choose how to handle them.
    """
    if not Config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(DDL)


async def init():
    """CLI entry: apply_migrations() + close the pool + emit a summary."""
    if not Config.DATABASE_URL:
        logger.error("DATABASE_URL is not set in .env")
        sys.exit(1)

    logger.info("Connecting to database...")
    await apply_migrations()

    logger.info("Tables created (or already exist):")
    logger.info("  - field_mappings")
    logger.info("  - enrichment_jobs")
    logger.info("  - enrichment_batches")
    logger.info("  - warm_path_runs")
    logger.info("  - contact_embeddings")
    logger.info("  - embedding_runs")
    logger.info("  - outreach_campaigns")
    logger.info("  - campaign_contacts")
    logger.info("  - campaign_templates")
    logger.info("  - batch_send_jobs")
    logger.info("  - campaign_files")
    logger.info("  - gmail_tokens")
    logger.info("  - email_suppressions")
    logger.info("  - email_bounces")

    await close_pool()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(init())
