"""
Backfill tier audience insights for existing campaigns.

Finds all campaigns in status=ready that have no insights yet,
generates a 1-2 sentence insight per tier, and saves them to the DB.

Usage (from project root):
    venv_312/Scripts/python.exe workspace/scripts/backfill_tier_insights.py

Flags:
    --dry-run   Print what would be generated without writing to DB.
    --campaign  Only backfill a specific campaign ID.
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import Config
from backend.db import client as db
from backend.db.client import get_pool, close_pool
from backend.outreach.signal_scanner import scan_tier_signals
from backend.outreach.template_generator import generate_tier_insight

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TIERS = ["tier_1", "tier_2", "tier_3"]


async def fetch_campaigns_needing_backfill(campaign_id: int | None) -> list[dict]:
    """Return campaigns that are ready and have at least one NULL insight."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if campaign_id:
            rows = await conn.fetch(
                """
                SELECT id, goal,
                       warm_intro_count   AS tier_1_count,
                       direct_count       AS tier_2_count,
                       reengagement_count AS tier_3_count,
                       tier_1_insight, tier_2_insight, tier_3_insight
                FROM outreach_campaigns
                WHERE id = $1 AND status = 'ready'
                """,
                campaign_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, goal,
                       warm_intro_count   AS tier_1_count,
                       direct_count       AS tier_2_count,
                       reengagement_count AS tier_3_count,
                       tier_1_insight, tier_2_insight, tier_3_insight
                FROM outreach_campaigns
                WHERE status = 'ready'
                  AND (tier_1_insight IS NULL
                       OR tier_2_insight IS NULL
                       OR tier_3_insight IS NULL)
                ORDER BY created_at DESC
                """,
            )
    return [dict(r) for r in rows]


async def backfill_campaign(campaign: dict, dry_run: bool, force: bool = False) -> None:
    cid  = campaign["id"]
    goal = campaign["goal"]
    logger.info(f"Campaign {cid}: {goal[:60]}")

    new_insights: dict[str, str] = {}

    for tier in TIERS:
        count_key = f"{tier}_count"
        existing  = campaign.get(f"{tier}_insight")

        if existing and not force:
            logger.info(f"  {tier}: already has insight — skipping (use --force to regenerate)")
            continue

        if not campaign.get(count_key, 0):
            logger.info(f"  {tier}: 0 contacts — skipping")
            continue

        logger.info(f"  {tier}: generating…")
        try:
            samples = await db.get_queue(cid, tier, include_later=True, offset=0, limit=20)
            scan    = await scan_tier_signals(cid, tier)
            insight = await generate_tier_insight(goal, tier, scan, samples)

            if insight:
                logger.info(f"  {tier}: \"{insight[:80]}{'…' if len(insight) > 80 else ''}\"")
                new_insights[tier] = insight
            else:
                logger.warning(f"  {tier}: returned empty — will leave NULL")
        except Exception as e:
            logger.error(f"  {tier}: failed — {e}")

    if not new_insights:
        logger.info(f"  Nothing new to save for campaign {cid}")
        return

    if dry_run:
        logger.info(f"  [dry-run] Would save: {list(new_insights.keys())}")
        return

    await db.save_tier_insights(
        cid,
        tier_1_insight=new_insights.get("tier_1", ""),
        tier_2_insight=new_insights.get("tier_2", ""),
        tier_3_insight=new_insights.get("tier_3", ""),
    )
    logger.info(f"  Saved insights for campaign {cid}")


async def main(campaign_id: int | None, dry_run: bool, force: bool) -> None:
    if not Config.DATABASE_URL:
        logger.error("DATABASE_URL not set in .env")
        sys.exit(1)
    if not Config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in .env")
        sys.exit(1)

    campaigns = await fetch_campaigns_needing_backfill(campaign_id if not force else None)

    # When forcing, fetch the specific campaign even if it already has insights
    if force and campaign_id:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, goal,
                       warm_intro_count   AS tier_1_count,
                       direct_count       AS tier_2_count,
                       reengagement_count AS tier_3_count,
                       tier_1_insight, tier_2_insight, tier_3_insight
                FROM outreach_campaigns
                WHERE id = $1 AND status = 'ready'
                """,
                campaign_id,
            )
        campaigns = [dict(r) for r in rows]

    if not campaigns:
        logger.info("No campaigns found to backfill.")
        await close_pool()
        return

    logger.info(f"Found {len(campaigns)} campaign(s){' (dry-run)' if dry_run else ''}{' (force)' if force else ''}")

    for c in campaigns:
        await backfill_campaign(c, dry_run, force=force)

    await close_pool()
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill tier insights for existing campaigns.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be generated, no DB writes.")
    parser.add_argument("--force",   action="store_true", help="Regenerate even if insight already exists.")
    parser.add_argument("--campaign", type=int, default=None, metavar="ID", help="Backfill a specific campaign ID only.")
    args = parser.parse_args()

    asyncio.run(main(campaign_id=args.campaign, dry_run=args.dry_run, force=args.force))
