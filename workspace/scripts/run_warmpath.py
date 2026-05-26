"""
Full warm path pipeline: load → match → write.

Usage:
  python workspace/scripts/run_warmpath.py --dry-run
  python workspace/scripts/run_warmpath.py
  python workspace/scripts/run_warmpath.py --top 5 --base-id appXXX --table-id tblXXX
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.config import Config
from backend.crm.airtable import AirtableClient
from backend.intelligence.warmpath.parser import load_contacts
from backend.intelligence.warmpath.matcher import build_index, run as match_run
from backend.intelligence.warmpath.writer import ensure_fields, write

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-id",  default=Config.AIRTABLE_BASE_ID)
    ap.add_argument("--table-id", default="tblJ0JMa1VxSLBHa7")
    ap.add_argument("--top",      type=int, default=3, help="Evidence lines per target")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    print(f"Base  : {args.base_id}")
    print(f"Table : {args.table_id}")
    print(f"Mode  : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    crm   = AirtableClient()
    table = crm.api.table(args.base_id, args.table_id)

    # ── Step 1: Load ──────────────────────────────────────────────────────
    t0 = time.time()
    print("Loading contacts from Airtable...")
    contacts, skipped = load_contacts(table)
    print(f"  {len(contacts)} loaded, {skipped} skipped  ({time.time()-t0:.1f}s)")

    targets = sum(1 for c in contacts if c.is_target)
    bridge  = len(contacts) - targets
    print(f"  {targets} targets (Tier 1/2), {bridge} bridge-only contacts")

    # ── Step 2: Match ─────────────────────────────────────────────────────
    t1 = time.time()
    print("\nBuilding index and finding paths...")
    index   = build_index(contacts)
    results = match_run(contacts, top_n=args.top)
    print(f"  {len(index)} company buckets in index  ({time.time()-t1:.1f}s)")
    print(f"  {len(results)} targets with at least one path")
    print(f"  {targets - len(results)} targets with no paths (not enough data)")

    if not results:
        print("\nNothing to write.")
        return

    # score summary
    top_scores = [paths[0].score for paths in results.values() if paths]
    all_scores = [p.score for paths in results.values() for p in paths]
    print(f"\n  Score stats (top path per target):")
    print(f"    Min  : {min(top_scores)}")
    print(f"    Max  : {max(top_scores)}")
    print(f"    Avg  : {sum(top_scores)/len(top_scores):.1f}")

    buckets = {"80-100": 0, "60-79": 0, "40-59": 0, "0-39": 0}
    for s in all_scores:
        if s >= 80:   buckets["80-100"] += 1
        elif s >= 60: buckets["60-79"]  += 1
        elif s >= 40: buckets["40-59"]  += 1
        else:         buckets["0-39"]   += 1
    print(f"\n  All-paths score distribution:")
    for k, v in buckets.items():
        print(f"    {k}: {v}")

    # ── Step 3: Preview top results ───────────────────────────────────────
    print("\n  Sample paths:")
    from backend.crm.airtable import AirtableClient as _A
    contact_map = {c.record_id: c for c in contacts}
    sorted_results = sorted(results.items(), key=lambda kv: kv[1][0].score, reverse=True)
    for rid, paths in sorted_results[:5]:
        c = contact_map.get(rid)
        tier = "T1" if c and c.is_tier1 else "T2"
        print(f"\n  {c.name if c else rid}  [{tier}]")
        for i, p in enumerate(paths[:args.top], 1):
            print(f"    {i}. [{p.score:>3}]  {p.bridge_name:<28}  {p.evidence}")

    # ── Step 4: Ensure fields ─────────────────────────────────────────────
    if not args.dry_run:
        print("\nEnsuring warm path fields exist in Airtable...")
        ensure_fields(Config.AIRTABLE_API_KEY, args.base_id, args.table_id)

    # ── Step 5: Write ─────────────────────────────────────────────────────
    t2 = time.time()
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Writing {len(results)} records to Airtable...")
    written, errors = write(
        results, crm,
        base_id=args.base_id,
        table_id=args.table_id,
        dry_run=args.dry_run,
        top_n=args.top,
    )

    if args.dry_run:
        print(f"  {written} records would be written")
    else:
        print(f"  Written : {written}")
        print(f"  Errors  : {errors}")
        print(f"  Time    : {time.time()-t2:.1f}s")

    print(f"\nTotal time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
