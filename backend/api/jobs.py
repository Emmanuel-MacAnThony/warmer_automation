"""
Enrichment job endpoints — jobs, batches, warm-path, dedup, and embedding runs.
"""
import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])


class JobPreflightRequest(BaseModel):
    base_id: str
    table_id: str
    view_id: str
    batch_size: int = 100


class JobCreateRequest(BaseModel):
    base_id: str
    table_id: str
    view_id: str
    linkedin_url_field: str = "LinkedIn"
    name_field: str = "Name"
    batch_size: int = 100


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@router.post("/jobs/preflight")
async def jobs_preflight(request: JobPreflightRequest):
    """Fetch record count for a view and compute batch breakdown (no DB write)."""
    try:
        import math
        import asyncio as _asyncio
        from backend.infra.crm.airtable import AirtableClient
        client = AirtableClient()
        loop = _asyncio.get_event_loop()
        record_ids = await loop.run_in_executor(
            None, client.get_view_record_ids, request.base_id, request.table_id, request.view_id
        )
        record_count = len(record_ids)
        batch_count = math.ceil(record_count / request.batch_size) if record_count > 0 else 0
        return {"record_count": record_count, "batch_count": batch_count, "batch_size": request.batch_size}
    except Exception as e:
        logger.error(f"Preflight failed: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/jobs/create")
async def jobs_create(request: JobCreateRequest):
    """Fetch all record IDs from the view, create enrichment_job + enrichment_batches in DB."""
    try:
        import math
        import asyncio as _asyncio
        from backend.infra.crm.airtable import AirtableClient
        from backend.infra.db.job_repo import get_active_job, create_job, create_batches, get_batches

        active = await get_active_job(request.base_id, request.table_id)
        if active:
            return JSONResponse(
                status_code=409,
                content={"error": f"A job is already active for this table (id={active['id']}, status={active['status']})"},
            )

        client = AirtableClient()
        loop = _asyncio.get_event_loop()
        record_ids = await loop.run_in_executor(
            None, client.get_view_record_ids, request.base_id, request.table_id, request.view_id
        )
        record_count = len(record_ids)
        if record_count == 0:
            return JSONResponse(status_code=400, content={"error": "No records found in this view"})

        batch_size = request.batch_size
        chunks = [record_ids[i : i + batch_size] for i in range(0, record_count, batch_size)]
        total_batches = len(chunks)

        # Store only the two user-specified input columns; all output fields are fixed in code.
        field_mapping = {
            "linkedin_url_field": request.linkedin_url_field,
            "name_field": request.name_field,
        }

        job_id = await create_job(
            base_id=request.base_id,
            table_id=request.table_id,
            field_mapping=field_mapping,
            batch_size=batch_size,
            total_records=record_count,
            total_batches=total_batches,
        )
        await create_batches(job_id, chunks)
        batches = await get_batches(job_id)

        from backend.infra.db.job_repo import update_job_status
        from backend.pipeline.manager import get_manager
        await update_job_status(job_id, "running")
        await get_manager().submit(job_id)

        logger.info(f"Created and started job {job_id}: {record_count} records, {total_batches} batches")
        return {"job_id": job_id, "record_count": record_count, "total_batches": total_batches, "batch_size": batch_size, "batches": batches}
    except Exception as e:
        logger.error(f"Job create failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/jobs")
async def list_jobs(base_id: str, table_id: str):
    from backend.infra.db.job_repo import get_jobs
    try:
        jobs = await get_jobs(base_id, table_id)
        return {"jobs": jobs}
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/jobs/{job_id}/batches")
async def list_job_batches(job_id: int):
    """List all batches. Lazily backfills stats from CSV for legacy batches."""
    from backend.infra.db.job_repo import get_batches, update_batch
    from backend.pipeline.executor import _csv_path, _read_processed_stats
    try:
        batches = await get_batches(job_id)
        for b in batches:
            processed = b.get("processed") or 0
            hits = b.get("hits") or 0
            misses = b.get("misses") or 0
            failed = b.get("failed") or 0
            if processed > 0 and (hits + misses + failed) < processed:
                csv = _csv_path(job_id, b["id"])
                _, csv_hits, csv_misses, csv_failed = _read_processed_stats(csv)
                if csv_hits or csv_misses or csv_failed:
                    await update_batch(b["id"], hits=csv_hits, misses=csv_misses, failed=csv_failed)
                    b["hits"] = csv_hits
                    b["misses"] = csv_misses
                    b["failed"] = csv_failed
        return {"batches": batches}
    except Exception as e:
        logger.error(f"Failed to list batches for job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/jobs/{job_id}/failures")
async def list_job_failures(job_id: int):
    """Per-record failure reasons for a job, read from its batch CSVs."""
    from backend.infra.db.job_repo import get_batches
    from backend.pipeline.executor import read_job_failures
    try:
        batches = await get_batches(job_id)
        result = await asyncio.to_thread(read_job_failures, batches)
        return result
    except Exception as e:
        logger.error(f"Failed to read failures for job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int):
    from backend.infra.db.job_repo import delete_job as db_delete_job
    from backend.pipeline.manager import get_manager
    try:
        deleted = await db_delete_job(job_id)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
        # Cancel the running task immediately so it doesn't keep processing
        manager = get_manager()
        task = manager._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            manager._tasks.pop(job_id, None)
            logger.info(f"Job {job_id}: task cancelled on delete")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/jobs/{job_id}/run")
async def run_job(job_id: int):
    """Start or resume a job. Returns 409 if already running."""
    from backend.infra.db.job_repo import get_job, update_job_status
    try:
        job = await get_job(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
        if job["status"] == "running":
            return JSONResponse(status_code=409, content={"error": "Job is already running"})
        if job["status"] == "completed":
            return JSONResponse(status_code=409, content={"error": "Job is already completed"})

        await update_job_status(job_id, "running")
        from backend.pipeline.manager import get_manager
        await get_manager().submit(job_id)
        logger.info(f"Job {job_id}: submitted to ExecutorManager")
        return {"success": True, "job_id": job_id, "status": "running"}
    except Exception as e:
        logger.error(f"Failed to run job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.patch("/jobs/{job_id}/status")
async def update_job_status_endpoint(job_id: int, body: dict[str, Any]):
    """Update job status (pause, pending, cancel)."""
    from backend.infra.db.job_repo import get_job, update_job_status
    try:
        status = body.get("status")
        if status not in ("paused", "pending", "cancelled"):
            return JSONResponse(status_code=400, content={"error": f"Invalid status '{status}'"})
        job = await get_job(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
        await update_job_status(job_id, status)
        logger.info(f"Job {job_id} status updated to {status}")
        return {"success": True, "job_id": job_id, "status": status}
    except Exception as e:
        logger.error(f"Failed to update job {job_id} status: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.patch("/jobs/{job_id}/batches/{batch_id}/status")
async def update_batch_status(job_id: int, batch_id: int, body: dict[str, Any]):
    from backend.infra.db.job_repo import update_batch
    try:
        status = body.get("status")
        if status not in ("pending", "running", "paused", "completed", "failed"):
            return JSONResponse(status_code=400, content={"error": "Invalid status"})
        await update_batch(batch_id, status=status)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to update batch {batch_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/jobs/{job_id}/rerun")
async def rerun_job(job_id: int):
    """Reset a completed/failed/paused job for a fresh re-enrichment run."""
    from backend.infra.db.job_repo import get_job
    from backend.infra.db.pool import get_pool
    from backend.pipeline.executor import _csv_path
    try:
        job = await get_job(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
        if job["status"] == "running":
            return JSONResponse(status_code=409, content={"error": "Job is currently running — pause it first"})

        pool = await get_pool()
        async with pool.acquire() as conn:
            batch_ids = [r["id"] for r in await conn.fetch(
                "SELECT id FROM enrichment_batches WHERE job_id=$1", job_id
            )]
            await conn.execute(
                """UPDATE enrichment_batches
                   SET status='pending', processed=0, hits=0, misses=0, failed=0,
                       started_at=NULL, completed_at=NULL
                   WHERE job_id=$1""",
                job_id,
            )
            await conn.execute(
                "UPDATE enrichment_jobs SET status='pending', updated_at=now() WHERE id=$1",
                job_id,
            )

        for bid in batch_ids:
            csv = _csv_path(job_id, bid)
            try:
                if os.path.exists(csv):
                    os.remove(csv)
            except Exception:
                pass

        logger.info(f"Job {job_id}: reset for re-run ({len(batch_ids)} batches cleared)")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to rerun job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.post("/jobs/{job_id}/reset-incomplete-batches")
async def reset_incomplete_batches(job_id: int):
    """Reset batches that are marked completed/paused but haven't finished processing all records."""
    from backend.infra.db.pool import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE enrichment_batches
                SET status = 'pending', completed_at = NULL
                WHERE job_id = $1
                  AND status IN ('completed', 'paused')
                  AND processed < total
                """,
                job_id,
            )
        count = int(result.split()[-1])
        logger.info(f"Job {job_id}: reset {count} incomplete batch(es) to pending")
        return {"success": True, "reset_count": count}
    except Exception as e:
        logger.error(f"Failed to reset incomplete batches for job {job_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ---------------------------------------------------------------------------
# Warm Path
# ---------------------------------------------------------------------------

@router.post("/warm-path/run")
async def warm_path_run(body: dict[str, Any]):
    """Manually trigger a warm path computation run."""
    job_id   = body.get("job_id")
    base_id  = body.get("base_id")
    table_id = body.get("table_id")

    if not job_id and not (base_id and table_id):
        return JSONResponse(status_code=400, content={"error": "job_id or base_id+table_id required"})

    try:
        enrichment_job_id = None
        if job_id:
            from backend.infra.db.job_repo import get_job
            job = await get_job(int(job_id))
            if not job:
                return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
            base_id  = job["base_id"]
            table_id = job["table_id"]
            enrichment_job_id = int(job_id)

        from backend.pipeline.warmpath_executor import run as run_warm_path
        asyncio.create_task(
            run_warm_path(base_id=base_id, table_id=table_id, triggered_by="manual", enrichment_job_id=enrichment_job_id)
        )
        return {"success": True, "message": "Warm path computation started"}
    except Exception as e:
        logger.error(f"Failed to trigger warm path: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/warm-path/status")
async def warm_path_status(
    job_id: Optional[int] = None,
    base_id: Optional[str] = None,
    table_id: Optional[str] = None,
):
    try:
        if job_id:
            from backend.infra.db.job_repo import get_warm_path_run_by_job
            run = await get_warm_path_run_by_job(job_id)
        elif base_id and table_id:
            from backend.infra.db.job_repo import get_latest_warm_path_run
            run = await get_latest_warm_path_run(base_id, table_id)
        else:
            return JSONResponse(status_code=400, content={"error": "job_id or base_id+table_id required"})
        return {"run": run}
    except Exception as e:
        logger.error(f"Failed to get warm path status: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------

@router.post("/dedup/run")
async def dedup_run(body: dict[str, Any]):
    """Trigger an async dedup health-check."""
    job_id   = body.get("job_id")
    base_id  = body.get("base_id")
    table_id = body.get("table_id")
    field_mapping: dict = {}

    if job_id:
        from backend.infra.db.job_repo import get_job
        job = await get_job(int(job_id))
        if not job:
            return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
        base_id       = job["base_id"]
        table_id      = job["table_id"]
        field_mapping = job.get("field_mapping") or {}
        enrichment_job_id = int(job_id)
    elif base_id and table_id:
        enrichment_job_id = None
    else:
        return JSONResponse(status_code=400, content={"error": "job_id or base_id+table_id required"})

    try:
        from backend.pipeline.dedup_executor import run as run_dedup
        asyncio.create_task(
            run_dedup(base_id=base_id, table_id=table_id, field_mapping=field_mapping,
                      triggered_by="manual", enrichment_job_id=enrichment_job_id)
        )
        return {"success": True, "message": "Dedup health-check started"}
    except Exception as e:
        logger.error(f"Failed to trigger dedup: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/dedup/status")
async def dedup_status(
    job_id: Optional[int] = None,
    base_id: Optional[str] = None,
    table_id: Optional[str] = None,
):
    try:
        if job_id:
            from backend.infra.db.job_repo import get_dedup_run_by_job
            run = await get_dedup_run_by_job(job_id)
        elif base_id and table_id:
            from backend.infra.db.job_repo import get_latest_dedup_run
            run = await get_latest_dedup_run(base_id, table_id)
        else:
            return JSONResponse(status_code=400, content={"error": "job_id or base_id+table_id required"})
        return {"run": run}
    except Exception as e:
        logger.error(f"Failed to get dedup status: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

@router.post("/embedding/run")
async def embedding_run(body: dict[str, Any]):
    """Manually trigger an embedding indexing run."""
    job_id   = body.get("job_id")
    base_id  = body.get("base_id")
    table_id = body.get("table_id")

    if not job_id and not (base_id and table_id):
        return JSONResponse(status_code=400, content={"error": "job_id or base_id+table_id required"})

    try:
        enrichment_job_id = None
        if job_id:
            from backend.infra.db.job_repo import get_job
            job = await get_job(int(job_id))
            if not job:
                return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
            base_id  = job["base_id"]
            table_id = job["table_id"]
            enrichment_job_id = int(job_id)

        from backend.pipeline.embedding_executor import run as run_embedding
        asyncio.create_task(
            run_embedding(base_id=base_id, table_id=table_id, triggered_by="manual", enrichment_job_id=enrichment_job_id)
        )
        return {"success": True, "message": "Embedding indexing started"}
    except Exception as e:
        logger.error(f"Failed to trigger embedding run: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/embedding/status")
async def embedding_status(
    job_id: Optional[int] = None,
    base_id: Optional[str] = None,
    table_id: Optional[str] = None,
):
    try:
        if job_id:
            from backend.infra.db.job_repo import get_embedding_run_by_job
            run = await get_embedding_run_by_job(job_id)
        elif base_id and table_id:
            from backend.infra.db.job_repo import get_latest_embedding_run
            run = await get_latest_embedding_run(base_id, table_id)
        else:
            return JSONResponse(status_code=400, content={"error": "job_id or base_id+table_id required"})
        return {"run": run}
    except Exception as e:
        logger.error(f"Failed to get embedding status: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
