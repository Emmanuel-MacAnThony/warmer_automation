"""
WarmPathExecutor — runs the full warm path computation pipeline.

Called automatically after an enrichment job completes, or manually
via the API endpoint.

run(base_id, table_id, enrichment_job_id, triggered_by) -> run_id
"""

import asyncio
import logging
from functools import partial
from typing import Optional

from backend.config import Config
from backend.infra.crm.airtable import AirtableClient
from backend.infra.db import client as db
from backend.intelligence.warmpath.parser import load_contacts
from backend.intelligence.warmpath.matcher import build_index, run as match_run
from backend.intelligence.warmpath.writer import ensure_fields, write

logger = logging.getLogger(__name__)


async def run(
    base_id: str,
    table_id: str,
    enrichment_job_id: Optional[int] = None,
    triggered_by: str = "auto",
) -> int:
    """
    Execute the full warm path pipeline off the event loop so blocking
    Airtable HTTP calls and CPU-bound matching don't freeze the server.

      1. Create warm_path_runs record (status: running)
      2. Load all contacts from Airtable  [thread pool]
      3. Build index + compute paths      [thread pool]
      4. Ensure Airtable fields exist     [thread pool]
      5. Write results back               [thread pool]
      6. Update warm_path_runs (completed)

    Returns the warm_path_runs run_id.
    """
    loop = asyncio.get_event_loop()

    run_id = await db.create_warm_path_run(
        base_id=base_id,
        table_id=table_id,
        triggered_by=triggered_by,
        enrichment_job_id=enrichment_job_id,
    )
    await db.update_warm_path_run(run_id, status="running")

    try:
        crm   = AirtableClient()
        table = crm.api.table(base_id, table_id)

        # ── Load (blocking Airtable HTTP) ──────────────────────────────────
        logger.info(f"[warm_path run={run_id}] Loading contacts from {base_id}/{table_id}")
        contacts, skipped = await loop.run_in_executor(None, load_contacts, table)
        targets_found = sum(1 for c in contacts if c.is_target)
        logger.info(
            f"[warm_path run={run_id}] {len(contacts)} loaded, {skipped} skipped, "
            f"{targets_found} targets"
        )

        await db.update_warm_path_run(
            run_id,
            status="running",
            contacts_loaded=len(contacts),
            targets_found=targets_found,
        )

        # ── Match (CPU-bound) ──────────────────────────────────────────────
        logger.info(f"[warm_path run={run_id}] Building index and computing paths")
        await loop.run_in_executor(None, build_index, contacts)
        results = await loop.run_in_executor(None, partial(match_run, contacts, top_n=3))
        paths_found = len(results)
        logger.info(f"[warm_path run={run_id}] {paths_found} targets with paths")

        await db.update_warm_path_run(
            run_id, status="running",
            contacts_loaded=len(contacts),
            targets_found=targets_found,
            paths_found=paths_found,
        )

        # ── Write (blocking Airtable HTTP) ─────────────────────────────────
        if results:
            logger.info(f"[warm_path run={run_id}] Ensuring Airtable fields exist")
            await loop.run_in_executor(
                None, partial(ensure_fields, crm, base_id, table_id)
            )

            logger.info(f"[warm_path run={run_id}] Writing {paths_found} records to Airtable")
            written, errors = await loop.run_in_executor(
                None,
                partial(write, results, crm, base_id=base_id, table_id=table_id, top_n=3),
            )
            logger.info(f"[warm_path run={run_id}] Written {written}, errors {errors}")

        # ── Complete ───────────────────────────────────────────────────────
        await db.update_warm_path_run(
            run_id,
            status="completed",
            contacts_loaded=len(contacts),
            targets_found=targets_found,
            paths_found=paths_found,
        )
        logger.info(f"[warm_path run={run_id}] Completed")

    except Exception as e:
        logger.error(f"[warm_path run={run_id}] Failed: {e}", exc_info=True)
        await db.update_warm_path_run(run_id, status="failed", error=str(e))
        raise

    return run_id
