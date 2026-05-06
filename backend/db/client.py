"""
PostgreSQL database client for field mappings and enrichment jobs
"""
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import asyncpg
from backend.config import Config

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            Config.DATABASE_URL,
            min_size=2,
            max_size=20,
            max_inactive_connection_lifetime=300,  # recycle idle connections after 5 min
        )
        logger.info("DB pool created")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Field Mappings
# ---------------------------------------------------------------------------

async def save_field_mapping(base_id: str, table_id: str, name: str, mappings: Dict) -> int:
    """Insert a new named field mapping for a table. Returns the new mapping id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO field_mappings (base_id, table_id, name, mappings)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id
            """,
            base_id, table_id, name, json.dumps(mappings)
        )
    mapping_id = row["id"]
    logger.info(f"Saved mapping '{name}' (id={mapping_id}) for {base_id}/{table_id}")
    return mapping_id


async def get_field_mappings(base_id: str, table_id: str) -> List[Dict]:
    """Fetch all saved mappings for a table, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, mappings, created_at
            FROM field_mappings
            WHERE base_id=$1 AND table_id=$2
            ORDER BY created_at DESC
            """,
            base_id, table_id
        )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "mappings": json.loads(r["mappings"]) if isinstance(r["mappings"], str) else r["mappings"],
            "created_at": r["created_at"].isoformat()
        }
        for r in rows
    ]


async def get_field_mapping_by_id(mapping_id: int) -> Optional[Dict]:
    """Fetch a single mapping by id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, mappings, created_at FROM field_mappings WHERE id=$1",
            mapping_id
        )
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "mappings": json.loads(row["mappings"]) if isinstance(row["mappings"], str) else row["mappings"],
        "created_at": row["created_at"].isoformat()
    }


async def delete_field_mapping(mapping_id: int) -> bool:
    """Delete a mapping by id. Returns True if deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM field_mappings WHERE id=$1", mapping_id
        )
    return result == "DELETE 1"


# ---------------------------------------------------------------------------
# Enrichment Jobs
# ---------------------------------------------------------------------------

async def create_job(
    base_id: str,
    table_id: str,
    field_mapping: Dict,
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


async def get_jobs(base_id: str, table_id: str, limit: int = 20) -> List[Dict]:
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


async def get_job(job_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM enrichment_jobs WHERE id=$1", job_id)
    if row is None:
        return None
    return _job_row(row)


async def get_active_job(base_id: str, table_id: str) -> Optional[Dict]:
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
    if row is None:
        return None
    return _job_row(row)


async def update_job_status(job_id: int, status: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE enrichment_jobs SET status=$1, updated_at=now() WHERE id=$2",
            status, job_id
        )


def _job_row(row) -> Dict:
    d = dict(row)
    d["field_mapping"] = json.loads(d["field_mapping"]) if isinstance(d["field_mapping"], str) else d["field_mapping"]
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


# ---------------------------------------------------------------------------
# Enrichment Batches
# ---------------------------------------------------------------------------

async def create_batches(job_id: int, record_id_chunks: List[List[str]]) -> List[int]:
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


async def get_batches(job_id: int) -> List[Dict]:
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
            import asyncio as _asyncio
            await _asyncio.sleep(1)


async def get_batch(batch_id: int) -> Optional[Dict]:
    """Fetch a single batch by its globally unique id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM enrichment_batches WHERE id=$1", batch_id
        )
    if row is None:
        return None
    return _batch_row(row)


async def reset_stale_batches() -> int:
    """
    On server startup: reset mid-run state after a crash.
    - Batches that were 'running' → 'pending' (executor will re-pick, CSV deduplicates already-done records)
    - Jobs stay 'running' — ExecutorManager auto-resumes them on boot, no operator action needed.
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


async def get_running_jobs() -> List[Dict]:
    """
    Fetch all jobs that should be auto-resumed on server startup.
    Includes 'running' (server was killed mid-job) and 'paused'
    (may have been set by old server-shutdown code).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM enrichment_jobs WHERE status IN ('running', 'paused') ORDER BY updated_at ASC"
        )
    return [_job_row(r) for r in rows]


def _batch_row(row) -> Dict:
    d = dict(row)
    d["record_ids"] = json.loads(d["record_ids"]) if isinstance(d["record_ids"], str) else d["record_ids"]
    for k in ("started_at", "completed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
