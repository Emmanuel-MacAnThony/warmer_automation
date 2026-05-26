"""
ExecutorManager — singleton that owns all running BatchExecutor tasks.

Responsibilities:
- submit(job_id)      : start a job as a background asyncio task (idempotent)
- auto_resume()       : on server startup, re-submit any jobs left in 'running' state
- shutdown()          : on server shutdown, cancel all tasks gracefully

The manager intentionally does NOT hold any per-job state beyond the asyncio.Task
reference — all durable state lives in the DB (enrichment_jobs / enrichment_batches).
"""

import asyncio
import logging
from typing import Dict

from backend.infra.db import client as db
from backend.pipeline.executor import BatchExecutor

logger = logging.getLogger(__name__)


class ExecutorManager:
    def __init__(self):
        # job_id -> asyncio.Task
        self._tasks: Dict[int, asyncio.Task] = {}

    async def submit(self, job_id: int) -> bool:
        """
        Submit a job for execution. Returns False if already running.
        The job must already be in 'running' status in the DB — the caller
        (API endpoint) is responsible for setting that before calling submit().
        """
        if job_id in self._tasks and not self._tasks[job_id].done():
            logger.info(f"Job {job_id}: already running, skip submit")
            return False

        job = await db.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id}: not found in DB, cannot submit")
            return False

        task = asyncio.create_task(
            self._run(job),
            name=f"job-{job_id}",
        )
        self._tasks[job_id] = task
        logger.info(f"Job {job_id}: submitted as background task")
        return True

    async def _run(self, job: dict) -> None:
        """Wrapper around BatchExecutor.run_job — catches and logs any unhandled error."""
        job_id = job["id"]
        try:
            executor = BatchExecutor()
            await executor.run_job(job)

            # Check if job completed successfully before triggering downstream pipeline
            completed_job = await db.get_job(job_id)
            if completed_job and completed_job["status"] == "completed":
                await self._trigger_post_enrichment(completed_job)

        except asyncio.CancelledError:
            # Server shutdown — leave status as "running" so auto_resume picks it up on restart.
            # (User-initiated pauses are set via DB polling in BatchExecutor, not here.)
            logger.info(
                f"Job {job_id}: task cancelled (server shutdown), status stays 'running' for auto-resume"
            )
            raise  # let asyncio clean up
        except Exception as e:
            logger.error(
                f"Job {job_id}: unhandled error in executor: {e}", exc_info=True
            )
            await db.update_job_status(job_id, "failed")
        finally:
            self._tasks.pop(job_id, None)

    async def _trigger_post_enrichment(self, job: dict) -> None:
        """
        Fire warm path + embedding indexing after a job completes.
        Both run independently — a failure in one does not affect the other.
        """
        job_id = job["id"]
        base_id = job["base_id"]
        table_id = job["table_id"]

        logger.info(f"Job {job_id}: triggering post-enrichment pipeline (warm path + embedding)")

        from backend.pipeline.warmpath_executor import run as run_warm_path
        from backend.pipeline.embedding_executor import run as run_embedding

        asyncio.create_task(
            _safe_run(
                run_warm_path(
                    base_id=base_id,
                    table_id=table_id,
                    triggered_by="auto",
                    enrichment_job_id=job_id,
                ),
                label=f"warm_path job={job_id}",
            )
        )

        asyncio.create_task(
            _safe_run(
                run_embedding(
                    base_id=base_id,
                    table_id=table_id,
                    triggered_by="auto",
                    enrichment_job_id=job_id,
                ),
                label=f"embedding job={job_id}",
            )
        )

    async def auto_resume(self) -> int:
        """
        Called once on server startup. Re-submits any job that was 'running'
        when the server went down (crash recovery). The DB already reset stale
        batches to 'pending' before this is called, so run_job will pick them up.
        Returns the number of jobs resumed.
        """
        running_jobs = await db.get_running_jobs()
        count = 0
        for job in running_jobs:
            submitted = await self.submit(job["id"])
            if submitted:
                count += 1
        if count:
            logger.info(f"ExecutorManager: auto-resumed {count} job(s) after startup")
        return count

    async def shutdown(self) -> None:
        """Cancel all running tasks and wait for them to finish."""
        active = {jid: t for jid, t in self._tasks.items() if not t.done()}
        if not active:
            return

        logger.info(f"ExecutorManager: cancelling {len(active)} job task(s)")
        for task in active.values():
            task.cancel()

        await asyncio.gather(*active.values(), return_exceptions=True)
        logger.info("ExecutorManager: all tasks cancelled")

    @property
    def running_job_ids(self):
        return [jid for jid, t in self._tasks.items() if not t.done()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _safe_run(coro, label: str) -> None:
    """Run a coroutine as a fire-and-forget task, logging any failure without propagating."""
    try:
        await coro
    except Exception as e:
        logger.error(f"Post-enrichment task '{label}' failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: ExecutorManager | None = None


def get_manager() -> ExecutorManager:
    global _manager
    if _manager is None:
        _manager = ExecutorManager()
    return _manager
