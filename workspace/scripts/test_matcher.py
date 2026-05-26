"""
Test the warm path matcher against real Airtable data.

Usage:
  python workspace/scripts/test_matcher.py
  python workspace/scripts/test_matcher.py --top 10
  python workspace/scripts/test_matcher.py --target "Emmett Shear"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.config import Config
from backend.crm.airtable import AirtableClient
from backend.intelligence.warmpath.parser import load_contacts
from backend.intelligence.warmpath.matcher import build_index, find_paths, run

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"   # fundraising_test_table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top",    type=int, default=5,  help="Paths per target")
    ap.add_argument("--target", type=str, default=None, help="Filter by contact name")
    args = ap.parse_args()

    print("Connecting to Airtable...")
    crm   = AirtableClient()
    table = crm.api.table(BASE_ID, TABLE_ID)

    print("Loading contacts...")
    contacts, skipped = load_contacts(table)
    print(f"  {len(contacts)} loaded, {skipped} skipped\n")

    index = build_index(contacts)
    print(f"Index: {len(index)} company buckets\n")

    # ── run ───────────────────────────────────────────────────────────────
    if args.target:
        targets = [c for c in contacts if args.target.lower() in c.name.lower()]
        if not targets:
            print(f"No contact matching '{args.target}'")
            return
        results = {}
        for t in targets:
            paths = find_paths(t, index, top_n=args.top)
            results[t.record_id] = paths
    else:
        results = run(contacts, top_n=args.top)

    # ── summary ───────────────────────────────────────────────────────────
    contact_map = {c.record_id: c for c in contacts}
    total_targets      = sum(1 for c in contacts if c.is_target)
    targets_with_paths = sum(1 for paths in results.values() if paths)

    print("=" * 70)
    print("  WARM PATH RESULTS")
    print("=" * 70)
    print(f"  Targets (Tier 1/2)     : {total_targets}")
    print(f"  With paths             : {targets_with_paths}")
    print(f"  No paths found         : {total_targets - targets_with_paths}")

    all_scores = [p.score for paths in results.values() for p in paths]
    if all_scores:
        top_scores = [paths[0].score for paths in results.values() if paths]
        print(f"  Score range            : {min(all_scores)} - {max(all_scores)}")
        print(f"  Avg best score/target  : {sum(top_scores) / len(top_scores):.1f}")

    # score distribution
    buckets = {"80-100": 0, "60-79": 0, "40-59": 0, "0-39": 0}
    for s in all_scores:
        if s >= 80:   buckets["80-100"] += 1
        elif s >= 60: buckets["60-79"]  += 1
        elif s >= 40: buckets["40-59"]  += 1
        else:         buckets["0-39"]   += 1

    print()
    for bucket, count in buckets.items():
        bar = "#" * count
        print(f"    {bucket}  {count:>4}  {bar}")
    print("=" * 70)

    # ── paths per target ──────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  TOP PATHS BY TARGET")
    print(f"{'=' * 70}")

    sorted_results = sorted(
        results.items(),
        key=lambda kv: kv[1][0].score if kv[1] else 0,
        reverse=True,
    )

    shown = 0
    for record_id, paths in sorted_results:
        target = contact_map.get(record_id)
        if not target:
            continue
        if not paths:
            continue

        tier = "T1" if target.is_tier1 else "T2"
        print(f"\n  {target.name}  [{tier} · {target.trajectory_tag}]")
        for i, p in enumerate(paths, 1):
            print(f"    {i}. [{p.score:>3}]  {p.bridge_name:<28}  {p.evidence}")

        shown += 1
        if not args.target and shown >= 20:
            remaining = targets_with_paths - shown
            if remaining > 0:
                print(f"\n  ... {remaining} more targets not shown (use --target NAME)")
            break

    # ── most used bridges ─────────────────────────────────────────────────
    bridge_usage: dict[str, int] = {}
    for paths in results.values():
        for p in paths:
            bridge_usage[p.bridge_id] = bridge_usage.get(p.bridge_id, 0) + 1

    if bridge_usage:
        print(f"\n{'=' * 70}")
        print("  MOST USED BRIDGES")
        print(f"{'=' * 70}")
        for bid, count in sorted(bridge_usage.items(), key=lambda x: -x[1])[:10]:
            c   = contact_map.get(bid)
            tag = c.trajectory_tag if c else ""
            print(f"  {count:>3}x  {(c.name if c else bid):<35}  [{tag}]")


if __name__ == "__main__":
    main()
