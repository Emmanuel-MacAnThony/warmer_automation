"""
End-to-end enrichment test for a single Airtable record.

Runs the full pipeline (fetch → scrape → LLM analyze → validate) for one record
and optionally writes results back to Airtable.

Usage:
    python workspace/scripts/test_enrich_record.py
    python workspace/scripts/test_enrich_record.py --dry-run
    python workspace/scripts/test_enrich_record.py --base-id appXXX --table-id tblXXX
    python workspace/scripts/test_enrich_record.py --record-id recXXXXXXXXXXXXXX
"""
import sys
import os
import asyncio
import logging
import csv
import argparse
from pathlib import Path

# ── sys.path: make backend/ importable ───────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]   # fundraising_automations/
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

from backend.config import Config
from backend.pipeline.executor import (
    BatchExecutor,
    _csv_field_names,
    _flush_csv_to_airtable_sync,
)
from backend.intelligence.linkedin.analyzer import PROFILE_SIGNAL_FIELDS, POST_SIGNAL_FIELDS
from backend.intelligence.news.analyzer import NEWS_SIGNAL_FIELDS
from backend.intelligence.twitter.analyzer import TWEET_SIGNAL_FIELDS

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_RECORD_ID = "rec2VHJn4VKZItuv0"
DEFAULT_BASE_ID   = Config.AIRTABLE_BASE_ID or ""
DEFAULT_TABLE_ID  = os.getenv("AIRTABLE_TABLE_NAME", "Contacts")

FIELD_MAPPING = {
    "linkedin_url_field": "LinkedIn",
    "name_field": "Name",
}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler()],
)
# Quiet noisy deps
for noisy in ("httpx", "httpcore", "openai", "anthropic", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("test_enrich_record")


async def main(record_id: str, base_id: str, table_id: str, dry_run: bool) -> None:
    separator = "=" * 64
    logger.info(separator)
    logger.info("  Single-Record Enrichment Test")
    logger.info(separator)
    logger.info(f"  Record : {record_id}")
    logger.info(f"  Base   : {base_id}")
    logger.info(f"  Table  : {table_id}")
    logger.info(f"  Dry-run: {dry_run}")
    logger.info(separator)

    if not base_id:
        logger.error("No base_id — set AIRTABLE_BASE_ID in backend/.env or pass --base-id")
        sys.exit(1)

    # Build CSV column list (mirrors _run_batch ordering in executor.py)
    field_cols          = _csv_field_names()
    profile_signal_cols = list(PROFILE_SIGNAL_FIELDS.keys())
    post_cols           = list(POST_SIGNAL_FIELDS.keys())
    news_cols           = list(NEWS_SIGNAL_FIELDS.keys())
    tweet_cols          = list(TWEET_SIGNAL_FIELDS.keys())

    csv_headers = (
        ["record_id", "linkedin_url", "status", "error"]
        + field_cols
        + profile_signal_cols
        + post_cols
        + news_cols
        + tweet_cols
    )

    # Write to a dedicated test directory so we don't mix with production batches
    out_dir = ROOT / "data" / "test_batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"test_{record_id}.csv"

    # Remove stale CSV from a previous run so results are fresh
    if csv_path.exists():
        csv_path.unlink()
        logger.info(f"Removed stale CSV: {csv_path.name}")

    logger.info("\nStarting pipeline…\n")
    executor = BatchExecutor()

    result = await executor._process_record(
        record_id, base_id, table_id, FIELD_MAPPING, csv_path, csv_headers
    )

    # ── Results ───────────────────────────────────────────────────────────────
    logger.info("\n" + separator)
    logger.info(f"  Pipeline result: {result!r}")
    logger.info(separator)

    if not csv_path.exists():
        logger.warning("CSV file was not created — nothing to show")
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        logger.warning("CSV is empty")
        return

    row = rows[-1]
    status = row.get("status", "")
    error  = row.get("error", "")

    logger.info(f"\n  status : {status}")
    if error:
        logger.info(f"  error  : {error}")

    if status == "success":
        logger.info("\n── Extracted fields ────────────────────────────────────────")
        skip = {"record_id", "status", "error"}
        groups = {
            "Profile (LLM)":  field_cols,
            "Career signals": profile_signal_cols,
            "Post signals":   post_cols,
            "News signals":   news_cols,
            "Tweet signals":  tweet_cols,
            "Misc":           ["linkedin_url"],
        }
        for group_name, cols in groups.items():
            populated = [(c, row[c]) for c in cols if c in row and row[c]]
            if not populated:
                continue
            logger.info(f"\n  [{group_name}]")
            for col, val in populated:
                display = val[:120] + ("…" if len(val) > 120 else "")
                logger.info(f"    {col:<42} {display}")

    # ── Flush to Airtable ─────────────────────────────────────────────────────
    if dry_run:
        logger.info(f"\n[dry-run] Skipping Airtable write — CSV saved to {csv_path}")
    elif status == "success":
        flush_cols = field_cols + profile_signal_cols + post_cols + news_cols + tweet_cols
        logger.info("\nFlushing to Airtable…")
        try:
            updated = _flush_csv_to_airtable_sync(base_id, table_id, csv_path, flush_cols)
            logger.info(f"✓ Updated {updated} record(s) in Airtable")
        except Exception as e:
            logger.error(f"Airtable flush failed: {e}")
    else:
        logger.info(f"\nSkipping Airtable flush (result={result})")

    logger.info(f"\nCSV saved to: {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test enrichment pipeline on one record")
    parser.add_argument("--record-id",  default=DEFAULT_RECORD_ID, help="Airtable record ID")
    parser.add_argument("--base-id",    default=DEFAULT_BASE_ID,   help="Airtable base ID (appXXX)")
    parser.add_argument("--table-id",   default=DEFAULT_TABLE_ID,  help="Airtable table ID or name")
    parser.add_argument("--dry-run",    action="store_true",        help="Skip writing back to Airtable")
    args = parser.parse_args()

    asyncio.run(main(args.record_id, args.base_id, args.table_id, args.dry_run))
