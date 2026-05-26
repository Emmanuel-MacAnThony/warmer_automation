"""
Enrichment job repository — jobs, batches, and background run tracking
(warm_path_runs, embedding_runs, dedup_runs).
Implements domain/interfaces/repos.py::JobRepo.
"""
import asyncio
import json
import logging
from typing import Any, Optional

import asyncpg

from backend.infra.db.pool import get_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enrichment Jobs
# ---------------------------------------------------------------------------

async def create_job(
    base_id: str,
    table_id: str,
    field_mapping: dict,
    batch_size: int,
    total_records: int,
    total_batches: int,
) -> int:
    """Create a new enrichment job. Returns job id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO enrichment_jobs
                (base_id, table_id, status, field_mapping, batch_size, total_records, total_batches)
            VALUES ($1, $2, 'pending', $3::jsonb, $4, $5, $6)
            RETURNING id
            """,
            base_id, table_id, json.dumps(field_mapping), batch_size, total_records, total_batches
        )
    job_id = row["id"]
    logger.info(f"Created job {job_id} for {base_id}/{table_id}")
    return job_id


async def get_jobs(base_id: str, table_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent jobs for a table, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM enrichment_jobs
            WHERE base_id=$1 AND table_id=$2
            ORDER BY created_at DESC LIMIT $3
            """,
            base_id, table_id, limit
        )
    return [_job_row(r) for r in rows]


async def get_job(job_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM enrichment_jobs WHERE id=$1", job_id)
    return _job_row(row) if row else None


async def delete_job(job_id: int) -> bool:
    """Delete a job and its batches (cascade). Returns True if deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM enrichment_jobs WHERE id=$1", job_id)
    return result == "DELETE 1"


async def get_active_job(base_id: str, table_id: str) -> Optional[dict[str, Any]]:
    """Return currently active (pending/running/paused) job for a table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM enrichment_jobs
            WHERE base_id=$1 AND table_id=$2
              AND status IN ('pending', 'running', 'paused')
            ORDER BY created_at DESC LIMIT 1
            """,
            base_id, table_id
        )
    return _job_row(row) if row else None


async def update_job_status(job_id: int, status: str, pause_reason: str | None = None) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE enrichment_jobs
               SET status=$1,
                   pause_reason=CASE WHEN $1='paused' THEN $3 ELSE NULL END,
                   updated_at=now()
               WHERE id=$2""",
            status, job_id, pause_reason,
        )


async def get_running_jobs() -> list[dict[str, Any]]:
    """
    Fetch all jobs that should be auto-resumed on server startup.
    Includes 'running' (server was killed mid-job) and 'paused'.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM enrichment_jobs WHERE status IN ('running', 'paused') ORDER BY updated_at ASC"
        )
    return [_job_row(r) for r in rows]


def _job_row(row) -> dict[str, Any]:
    d = dict(row)
    d["field_mapping"] = json.loads(d["field_mapping"]) if isinstance(d["field_mapping"], str) else d["field_mapping"]
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Enrichment Batches
# ---------------------------------------------------------------------------

async def create_batches(job_id: int, record_id_chunks: list[list[str]]) -> list[int]:
    """Insert all batches for a job (status=pending). Returns list of batch ids."""
    pool = await get_pool()
    batch_ids = []
    async with pool.acquire() as conn:
        for i, chunk in enumerate(record_id_chunks, start=1):
            row = await conn.fetchrow(
                """
                INSERT INTO enrichment_batches
                    (job_id, batch_number, status, record_ids, total)
                VALUES ($1, $2, 'pending', $3::jsonb, $4)
                RETURNING id
                """,
                job_id, i, json.dumps(chunk), len(chunk)
            )
            batch_ids.append(row["id"])
    logger.info(f"Created {len(batch_ids)} batches for job {job_id}")
    return batch_ids


async def get_batches(job_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM enrichment_batches WHERE job_id=$1 ORDER BY batch_number",
            job_id
        )
    return [_batch_row(r) for r in rows]


async def update_batch(batch_id: int, **fields) -> None:
    """Update arbitrary fields on a batch row."""
    if not fields:
        return
    pool = await get_pool()
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())
    for attempt in range(3):
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    f"UPDATE enrichment_batches SET {sets} WHERE id=$1",
                    batch_id, *values
                )
            return
        except (asyncpg.ConnectionDoesNotExistError, OSError) as e:
            if attempt == 2:
                raise
            logger.warning(f"update_batch: connection error on attempt {attempt + 1}, retrying: {e}")
            await asyncio.sleep(1)


async def save_batch_failures(batch_id: int, failures: list[dict]) -> None:
    """Persist per-record failure reasons for a batch (JSONB). Durable across restarts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE enrichment_batches SET failures=$2::jsonb WHERE id=$1",
            batch_id, json.dumps(failures),
        )


async def get_batch(batch_id: int) -> Optional[dict[str, Any]]:
    """Fetch a single batch by its globally unique id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM enrichment_batches WHERE id=$1", batch_id
        )
    return _batch_row(row) if row else None


async def reset_stale_batches() -> int:
    """
    On server startup: reset mid-run state after a crash.
    Batches that were 'running' → 'pending'; jobs stay 'running' (auto-resume).
    Returns count of reset batches.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        batch_result = await conn.execute(
            "UPDATE enrichment_batches SET status='pending' WHERE status='running'"
        )
    batch_count = int(batch_result.split()[-1])
    if batch_count:
        logger.info(
            f"Startup recovery: reset {batch_count} batches running → pending (jobs stay running, auto-resume)"
        )
    return batch_count


async def reset_stale_pipeline_runs() -> tuple[int, int]:
    """
    On server startup: mark any embedding_run or warm_path_run stuck in 'running'
    as failed so the UI shows the Run button again instead of a frozen progress bar.
    Returns (embedding_count, warm_path_count) reset.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        emb_result = await conn.execute(
            "UPDATE embedding_runs SET status='failed', error='Server restarted' WHERE status='running'"
        )
        wp_result = await conn.execute(
            "UPDATE warm_path_runs SET status='failed', error='Server restarted' WHERE status='running'"
        )
    emb_count = int(emb_result.split()[-1])
    wp_count  = int(wp_result.split()[-1])
    return emb_count, wp_count


def _batch_row(row) -> dict[str, Any]:
    d = dict(row)
    d["record_ids"] = json.loads(d["record_ids"]) if isinstance(d["record_ids"], str) else d["record_ids"]
    if "failures" in d:
        d["failures"] = json.loads(d["failures"]) if isinstance(d["failures"], str) else (d["failures"] or [])
    for k in ("started_at", "completed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Warm Path Runs
# ---------------------------------------------------------------------------

async def create_warm_path_run(
    base_id: str,
    table_id: str,
    triggered_by: str = "auto",
    enrichment_job_id: Optional[int] = None,
) -> int:
    """Create a warm path run record. Returns run id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO warm_path_runs (base_id, table_id, triggered_by, enrichment_job_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            base_id, table_id, triggered_by, enrichment_job_id,
        )
    run_id = row["id"]
    logger.info(f"Created warm_path_run {run_id} ({triggered_by}) for {base_id}/{table_id}")
    return run_id


async def update_warm_path_run(
    run_id: int,
    status: str,
    contacts_loaded: Optional[int] = None,
    targets_found: Optional[int] = None,
    paths_found: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE warm_path_runs SET
                status          = $1,
                contacts_loaded = COALESCE($2, contacts_loaded),
                targets_found   = COALESCE($3, targets_found),
                paths_found     = COALESCE($4, paths_found),
                error           = COALESCE($5, error),
                completed_at    = CASE WHEN $1 IN ('completed', 'failed') THEN now() ELSE completed_at END
            WHERE id = $6
            """,
            status, contacts_loaded, targets_found, paths_found, error, run_id,
        )


async def get_latest_warm_path_run(base_id: str, table_id: str) -> Optional[dict[str, Any]]:
    """Return the most recent warm path run for a table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM warm_path_runs
            WHERE base_id=$1 AND table_id=$2
            ORDER BY created_at DESC LIMIT 1
            """,
            base_id, table_id,
        )
    return _warm_path_row(row) if row else None


async def get_warm_path_run_by_job(job_id: int) -> Optional[dict[str, Any]]:
    """Return the most recent warm path run for a specific enrichment job."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM warm_path_runs
            WHERE enrichment_job_id = $1
            ORDER BY created_at DESC LIMIT 1
            """,
            job_id,
        )
    return _warm_path_row(row) if row else None


async def get_warm_path_runs(base_id: str, table_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent warm path runs for a table, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM warm_path_runs
            WHERE base_id=$1 AND table_id=$2
            ORDER BY created_at DESC LIMIT $3
            """,
            base_id, table_id, limit,
        )
    return [_warm_path_row(r) for r in rows]


def _warm_path_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("created_at", "completed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Embedding Runs
# ---------------------------------------------------------------------------

async def create_embedding_run(
    base_id: str,
    table_id: str,
    triggered_by: str = "auto",
    enrichment_job_id: Optional[int] = None,
) -> int:
    """Create an embedding run record. Returns run id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO embedding_runs (base_id, table_id, triggered_by, enrichment_job_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            base_id, table_id, triggered_by, enrichment_job_id,
        )
    run_id = row["id"]
    logger.info(f"Created embedding_run {run_id} ({triggered_by}) for {base_id}/{table_id}")
    return run_id


async def update_embedding_run(
    run_id: int,
    status: str,
    total_contacts: Optional[int] = None,
    indexed: Optional[int] = None,
    skipped: Optional[int] = None,
    failed: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE embedding_runs SET
                status         = $1,
                total_contacts = COALESCE($2, total_contacts),
                indexed        = COALESCE($3, indexed),
                skipped        = COALESCE($4, skipped),
                failed         = COALESCE($5, failed),
                error          = COALESCE($6, error),
                completed_at   = CASE WHEN $1 IN ('completed', 'failed') THEN now() ELSE completed_at END
            WHERE id = $7
            """,
            status, total_contacts, indexed, skipped, failed, error, run_id,
        )


async def get_embedding_run_by_job(job_id: int) -> Optional[dict[str, Any]]:
    """Return the most recent embedding run for a specific enrichment job."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM embedding_runs
            WHERE enrichment_job_id = $1
            ORDER BY created_at DESC LIMIT 1
            """,
            job_id,
        )
    return _embedding_run_row(row) if row else None


async def get_latest_embedding_run(base_id: str, table_id: str) -> Optional[dict[str, Any]]:
    """Return the most recent embedding run for a table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM embedding_runs
            WHERE base_id=$1 AND table_id=$2
            ORDER BY created_at DESC LIMIT 1
            """,
            base_id, table_id,
        )
    return _embedding_run_row(row) if row else None


def _embedding_run_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("created_at", "completed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Dedup Runs
# ---------------------------------------------------------------------------

async def create_dedup_run(
    base_id: str,
    table_id: str,
    triggered_by: str = "auto",
    enrichment_job_id: Optional[int] = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dedup_runs (base_id, table_id, triggered_by, enrichment_job_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            base_id, table_id, triggered_by, enrichment_job_id,
        )
    run_id = row["id"]
    logger.info(f"Created dedup_run {run_id} ({triggered_by}) for {base_id}/{table_id}")
    return run_id


async def update_dedup_run(
    run_id: int,
    status: str,
    records_checked: Optional[int] = None,
    groups_found: Optional[int] = None,
    records_deleted: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE dedup_runs SET
                status          = $1,
                records_checked = COALESCE($2, records_checked),
                groups_found    = COALESCE($3, groups_found),
                records_deleted = COALESCE($4, records_deleted),
                error           = COALESCE($5, error),
                completed_at    = CASE WHEN $1 IN ('completed', 'failed') THEN now() ELSE completed_at END
            WHERE id = $6
            """,
            status, records_checked, groups_found, records_deleted, error, run_id,
        )


async def get_dedup_run_by_job(job_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM dedup_runs WHERE enrichment_job_id=$1 ORDER BY created_at DESC LIMIT 1",
            job_id,
        )
    return _dedup_run_row(row) if row else None


async def get_latest_dedup_run(base_id: str, table_id: str) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM dedup_runs WHERE base_id=$1 AND table_id=$2 ORDER BY created_at DESC LIMIT 1",
            base_id, table_id,
        )
    return _dedup_run_row(row) if row else None


async def reset_stale_dedup_runs() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE dedup_runs SET status='failed', error='Server restarted' WHERE status IN ('running','pending')"
        )
    return int(result.split()[-1])


def _dedup_run_row(row) -> dict[str, Any]:
    d = dict(row)
    for k in ("created_at", "completed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
