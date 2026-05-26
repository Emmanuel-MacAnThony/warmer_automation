"""
Tests for ExecutorManager — the job-level orchestrator.

ExecutorManager is what replaces an event bus here:
  - submit(job_id) creates an asyncio.Task for BatchExecutor.run_job (idempotent)
  - When run_job completes successfully, _trigger_post_enrichment fires
    warmpath_executor and embedding_executor as independent fire-and-forget tasks
  - auto_resume() re-submits any jobs left in 'running' state after a server restart
  - shutdown() cancels all active tasks

These tests verify those orchestration decisions without touching
Airtable, Apify, or the LLM.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.pipeline.manager import ExecutorManager


# ─────────────────────────────────────────────────────────────────────────────
# submit — idempotency and job lookup
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_submit_returns_false_when_already_running():
    """Submitting the same job_id twice while it's still running returns False."""
    manager = ExecutorManager()

    async def slow_job():
        await asyncio.sleep(10)

    manager._tasks[42] = asyncio.create_task(slow_job())

    with patch("backend.pipeline.manager.db") as mock_db:
        mock_db.get_job = AsyncMock(return_value={"id": 42})
        result = await manager.submit(42)

    assert result is False
    # Clean up
    manager._tasks[42].cancel()
    await asyncio.gather(manager._tasks[42], return_exceptions=True)


@pytest.mark.anyio
async def test_submit_returns_false_when_job_not_in_db():
    """If the job_id doesn't exist in the DB, submit does nothing and returns False."""
    manager = ExecutorManager()
    with patch("backend.pipeline.manager.db") as mock_db:
        mock_db.get_job = AsyncMock(return_value=None)
        result = await manager.submit(999)
    assert result is False
    assert 999 not in manager._tasks


@pytest.mark.anyio
async def test_submit_creates_task_for_new_job():
    """Submitting a valid job_id that isn't running creates a background task."""
    manager = ExecutorManager()
    job = {"id": 7, "base_id": "appX", "table_id": "tblY", "field_mapping": {}}

    with (
        patch("backend.pipeline.manager.db") as mock_db,
        patch("backend.pipeline.manager.BatchExecutor") as mock_executor_cls,
    ):
        mock_db.get_job = AsyncMock(return_value=job)
        mock_db.update_job_status = AsyncMock()
        mock_db.get_job_status = AsyncMock(return_value={"status": "completed"})

        mock_executor = MagicMock()
        mock_executor.run_job = AsyncMock()
        mock_executor_cls.return_value = mock_executor

        result = await manager.submit(7)

    assert result is True
    assert 7 in manager._tasks
    # Let the task finish
    task = manager._tasks.get(7)
    if task:
        await asyncio.gather(task, return_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# auto_resume — crash recovery on startup
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_auto_resume_submits_running_jobs():
    """On startup, auto_resume re-submits every job that was 'running' when server died."""
    manager = ExecutorManager()
    running_jobs = [
        {"id": 1, "base_id": "appX", "table_id": "tblY", "field_mapping": {}},
        {"id": 2, "base_id": "appX", "table_id": "tblZ", "field_mapping": {}},
    ]

    with (
        patch("backend.pipeline.manager.db") as mock_db,
        patch.object(manager, "submit", new_callable=AsyncMock, return_value=True) as mock_submit,
    ):
        mock_db.get_running_jobs = AsyncMock(return_value=running_jobs)
        count = await manager.auto_resume()

    assert count == 2
    assert mock_submit.call_count == 2
    submitted_ids = {call.args[0] for call in mock_submit.call_args_list}
    assert submitted_ids == {1, 2}


@pytest.mark.anyio
async def test_auto_resume_returns_zero_when_no_running_jobs():
    manager = ExecutorManager()
    with patch("backend.pipeline.manager.db") as mock_db:
        mock_db.get_running_jobs = AsyncMock(return_value=[])
        count = await manager.auto_resume()
    assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Post-enrichment pipeline trigger
# When a job completes, warm path + embedding run as independent tasks.
# A failure in one must not prevent the other from running.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_trigger_post_enrichment_fires_both_tasks():
    """After job completion, both warm_path and embedding tasks are created.

    _trigger_post_enrichment imports the executors lazily, so patch at source.
    We track how many times each run() is called rather than awaiting tasks.
    """
    manager = ExecutorManager()
    job = {"id": 5, "base_id": "appX", "table_id": "tblY"}

    warm_path_mock = AsyncMock()
    embedding_mock = AsyncMock()

    with (
        patch("backend.pipeline.warmpath_executor.run", warm_path_mock),
        patch("backend.pipeline.embedding_executor.run", embedding_mock),
    ):
        before = set(asyncio.all_tasks())
        await manager._trigger_post_enrichment(job)
        # Drain new tasks created by _trigger_post_enrichment
        new_tasks = set(asyncio.all_tasks()) - before - {asyncio.current_task()}
        if new_tasks:
            await asyncio.gather(*new_tasks, return_exceptions=True)

    warm_path_mock.assert_called_once()
    embedding_mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# shutdown — graceful cancellation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_shutdown_cancels_active_tasks():
    """shutdown() cancels all running tasks and waits for them to finish."""
    manager = ExecutorManager()

    async def blocking():
        await asyncio.sleep(100)

    manager._tasks[1] = asyncio.create_task(blocking())
    manager._tasks[2] = asyncio.create_task(blocking())

    # Yield so tasks start executing before we cancel them
    await asyncio.sleep(0)

    await manager.shutdown()

    assert all(t.done() for t in manager._tasks.values())


@pytest.mark.anyio
async def test_shutdown_is_noop_when_no_tasks():
    manager = ExecutorManager()
    # Should not raise
    await manager.shutdown()
    assert manager.running_job_ids == []
