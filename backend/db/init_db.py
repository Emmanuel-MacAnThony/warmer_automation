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
from backend.db.client import get_pool, close_pool

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

-- Migrations: add columns introduced after initial deploy (idempotent)
ALTER TABLE enrichment_batches ADD COLUMN IF NOT EXISTS hits   INT NOT NULL DEFAULT 0;
ALTER TABLE enrichment_batches ADD COLUMN IF NOT EXISTS misses INT NOT NULL DEFAULT 0;
"""


async def init():
    if not Config.DATABASE_URL:
        logger.error("DATABASE_URL is not set in .env")
        sys.exit(1)

    logger.info("Connecting to database...")
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute(DDL)

    logger.info("Tables created (or already exist):")
    logger.info("  - field_mappings")
    logger.info("  - enrichment_jobs")
    logger.info("  - enrichment_batches")

    await close_pool()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(init())
