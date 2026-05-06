"""
Backfill news signals for already-enriched records.

Reads success rows from completed batch CSVs, runs news search for each
contact, and patches the 4 press fields directly in Airtable.

Usage:
    python scripts/backfill_news_signals.py          # all completed batches for job 2
    python scripts/backfill_news_signals.py 14       # specific batch DB id
"""

import asyncio
import csv
import json
import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.clients.airtable_client import AirtableClient
from backend.clients.serp_client import SerpClient
from backend.config import Config
from backend.db import client as db
from backend.enrichment.news_analyzer import parse_news_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

_serp_semaphore = asyncio.Semaphore(5)
_serp = SerpClient()
_airtable = AirtableClient()


async def _fetch_news(record_id: str, name: str, company: str, loop) -> Dict[str, Any]:
    if not name:
        return {}
    async with _serp_semaphore:
        results = await loop.run_in_executor(None, _serp.search_news, name, company)
    signals = parse_news_results(results, name)
    signals["_record_id"] = record_id
    return signals


def _read_success_rows(csv_path: Path) -> List[Dict]:
    """Return rows with status=success from a batch CSV. Last row wins per record_id."""
    if not csv_path.exists():
        return []
    latest: Dict[str, Dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "success" and row.get("record_id"):
                latest[row["record_id"]] = row
    return list(latest.values())


async def backfill(batch_ids: List[int]) -> None:
    loop = asyncio.get_event_loop()
    pool = await db.get_pool()

    for batch_id in batch_ids:
        batch = await pool.fetchrow(
            "SELECT id, job_id, batch_number FROM enrichment_batches WHERE id=$1", batch_id
        )
        if not batch:
            logger.warning(f"Batch {batch_id} not found")
            continue

        job = await pool.fetchrow(
            "SELECT base_id, table_id FROM enrichment_jobs WHERE id=$1", batch["job_id"]
        )
        base_id  = job["base_id"]
        table_id = job["table_id"]

        csv_path = Path(Config.BATCH_OUTPUT_DIR) / f"job_{batch['job_id']}_batch_{batch_id}.csv"
        rows = _read_success_rows(csv_path)
        if not rows:
            logger.info(f"Batch {batch_id}: no success rows found")
            continue

        logger.info(f"Batch {batch_id} (job {batch['job_id']} batch #{batch['batch_number']}): "
                    f"{len(rows)} records to backfill")

        # Run all news searches concurrently (semaphore limits to 5 at a time)
        tasks = [
            _fetch_news(
                r["record_id"],
                r.get("Name") or r.get("name") or "",
                r.get("Company Name") or r.get("company") or "",
                loop,
            )
            for r in rows
        ]
        results = await asyncio.gather(*tasks)

        # Build Airtable update payload — skip records with no news (press_count=0)
        updates = []
        skipped = 0
        for signals in results:
            rid = signals.pop("_record_id", None)
            if not rid:
                continue
            if signals.get("press_count", 0) == 0 and len(signals) == 1:
                skipped += 1
                continue
            fields = {k: v for k, v in signals.items() if v is not None}
            if fields:
                updates.append({"id": rid, "fields": fields})

        logger.info(f"Batch {batch_id}: {len(updates)} have news results, {skipped} no coverage")

        if updates:
            updated = _airtable.batch_update_in_table(base_id, table_id, updates)
            logger.info(f"Batch {batch_id}: synced {updated} records to Airtable")


async def main():
    pool = await db.get_pool()

    if len(sys.argv) > 1:
        batch_ids = [int(x) for x in sys.argv[1:]]
    else:
        # All completed batches for job 2
        rows = await pool.fetch(
            "SELECT id FROM enrichment_batches WHERE job_id=2 AND status='completed' ORDER BY batch_number"
        )
        batch_ids = [r["id"] for r in rows]

    if not batch_ids:
        logger.info("No completed batches found")
        return

    logger.info(f"Backfilling news signals for batch IDs: {batch_ids}")
    await backfill(batch_ids)
    logger.info("Done")


if __name__ == "__main__":
    asyncio.run(main())
