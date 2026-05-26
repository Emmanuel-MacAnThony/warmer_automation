"""
Backfill career_json for contacts that were enriched before the field was added.

The enrichment pipeline now writes career_json (structured role list for warm path
matching) alongside last_three_roles. Contacts enriched before that fix only have
last_three_roles — a human-readable text string.

This script parses last_three_roles back into structured JSON and writes career_json
to Airtable for all contacts that are missing it.

Format of last_three_roles (written by extract_career_progression):
  "Title at Company (start–end)"   e.g. "CTO at Stripe (2018–2022)"
  "Title at Company (start–present)"

Usage:
    python -m workspace.scripts.backfill_career_json
    python -m workspace.scripts.backfill_career_json --dry-run
    python -m workspace.scripts.backfill_career_json --limit 50
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import Config
from backend.crm.airtable import AirtableClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Matches: "Title at Company (2018–2022)" or "Title at Company (2018–present)"
# The en-dash (–) and plain hyphen (-) are both handled.
_ROLE_RE = re.compile(
    r'^(.+?)\s+at\s+(.+?)\s+\((\d{4})?[–\-](\d{4}|present)?\)\s*$',
    re.IGNORECASE,
)


def _parse_last_three_roles(text: str) -> list[dict]:
    """
    Parse last_three_roles text back into role dicts for career_json.
    Returns [] if the text is empty or unparseable.
    """
    if not text or not text.strip():
        return []

    roles = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = _ROLE_RE.match(line)
        if not m:
            logger.debug(f"  Could not parse role line: {line!r}")
            continue

        title, company, start_str, end_str = m.group(1), m.group(2), m.group(3), m.group(4)
        start = int(start_str) if start_str else None
        end   = int(end_str)   if end_str and end_str.lower() != "present" else None

        roles.append({"title": title.strip(), "company": company.strip(), "start": start, "end": end})

    return roles


def run(base_id: str, table_id: str, dry_run: bool = False, limit: Optional[int] = None) -> None:
    crm = AirtableClient()
    table = crm.api.table(base_id, table_id)

    logger.info(f"Fetching enriched contacts from {base_id}/{table_id}...")

    # Only filter on last_three_roles in the Airtable formula — check career_json in Python
    # to avoid formula failures on empty/null field state
    records = table.all(
        fields=["last_three_roles", "career_json"],
        formula="{last_three_roles} != ''",
    )

    logger.info(f"Found {len(records)} contacts with last_three_roles")

    if limit:
        records = records[:limit]
        logger.info(f"Limiting to first {limit}")

    updates = []
    already_set = 0
    unparseable = 0

    for rec in records:
        f = rec["fields"]

        # Skip if career_json already populated
        if (f.get("career_json") or "").strip():
            already_set += 1
            continue

        raw = (f.get("last_three_roles") or "").strip()
        if not raw:
            unparseable += 1
            continue

        roles = _parse_last_three_roles(raw)
        if not roles:
            logger.warning(f"  {rec['id']}: could not parse — {raw!r}")
            unparseable += 1
            continue

        updates.append({"id": rec["id"], "fields": {"career_json": json.dumps(roles)}})

    logger.info(f"To write: {len(updates)}  |  already set: {already_set}  |  unparseable: {unparseable}")

    if dry_run:
        logger.info("DRY RUN — showing first 5 results, no writes")
        for u in updates[:5]:
            print(f"\n  {u['id']}")
            for role in json.loads(u["fields"]["career_json"]):
                print(f"    {role}")
        return

    if not updates:
        logger.info("Nothing to write.")
        return

    # Batch update in chunks of 10 (Airtable limit)
    CHUNK = 10
    written = 0
    for i in range(0, len(updates), CHUNK):
        chunk = updates[i : i + CHUNK]
        try:
            table.batch_update(chunk, typecast=True)
            written += len(chunk)
            logger.info(f"  Written {written}/{len(updates)}")
        except Exception as e:
            logger.error(f"  Chunk {i//CHUNK + 1} failed: {e}")

    logger.info(f"Done — {written} contacts updated with career_json")


async def _get_table_id_from_db(base_id: str) -> Optional[str]:
    """Look up the real Airtable table ID from the most recent enrichment job for this base."""
    try:
        import asyncio
        from backend.db import client as db
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT table_id FROM enrichment_jobs WHERE base_id=$1 ORDER BY id DESC LIMIT 1",
                base_id,
            )
        return row["table_id"] if row else None
    except Exception:
        return None


if __name__ == "__main__":
    import asyncio as _asyncio

    parser = argparse.ArgumentParser(description="Backfill career_json from last_three_roles")
    parser.add_argument("--base-id",  default=Config.AIRTABLE_BASE_ID)
    parser.add_argument("--table-id", default=None, help="Airtable table ID (auto-resolved from DB if omitted)")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--limit",    type=int, default=None)
    args = parser.parse_args()

    if not args.base_id:
        print("ERROR: Set --base-id or AIRTABLE_BASE_ID in .env")
        sys.exit(1)

    table_id = args.table_id
    if not table_id:
        table_id = _asyncio.run(_get_table_id_from_db(args.base_id))
    if not table_id:
        print("ERROR: Could not resolve table ID — pass --table-id explicitly")
        sys.exit(1)

    logger.info(f"Using table ID: {table_id}")
    run(args.base_id, table_id, dry_run=args.dry_run, limit=args.limit)
