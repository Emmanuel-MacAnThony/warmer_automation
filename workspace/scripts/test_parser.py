"""
Test the warm path parser against real Airtable data.

Usage:
  python workspace/scripts/test_parser.py
  python workspace/scripts/test_parser.py --targets-only
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from backend.config import Config
from backend.crm.airtable import AirtableClient
from backend.intelligence.warmpath.parser import load_contacts

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets-only", action="store_true",
                    help="Only show Tier 1/2 contacts")
    args = ap.parse_args()

    tier_filter = "targets" if args.targets_only else None

    print(f"Connecting to Airtable ({TABLE_ID})...")
    crm   = AirtableClient()
    table = crm.api.table(BASE_ID, TABLE_ID)

    print("Loading contacts...\n")
    contacts, skipped = load_contacts(table, tier_filter=tier_filter)

    # ── Summary ──────────────────────────────────────────────────────────────
    tier_counts = Counter(c.trajectory_tag or "UNTAGGED" for c in contacts)
    role_counts = Counter(len(c.roles) for c in contacts)
    has_dates   = sum(1 for c in contacts if any(r.start for r in c.roles))

    print("=" * 60)
    print("  PARSER REPORT")
    print("=" * 60)
    print(f"  Contacts loaded      : {len(contacts)}")
    print(f"  Skipped (no roles)   : {skipped}")
    print(f"  With at least 1 date : {has_dates}")
    print()
    print("  By trajectory_tag:")
    for tag, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
        tier = "T1" if tag in ("EXITED_FOUNDER", "SERIAL_FOUNDER") else \
               "T2" if tag in ("SENIOR_OPERATOR", "RSU_BENEFICIARY") else "  "
        print(f"    {tier}  {tag:<30} {count}")
    print()
    print("  Roles per contact:")
    for count in sorted(role_counts):
        print(f"    {count} roles : {role_counts[count]} contacts")
    print("=" * 60)

    # ── Sample contacts ───────────────────────────────────────────────────────
    targets  = [c for c in contacts if c.is_target]
    bridges  = [c for c in contacts if not c.is_target]

    print(f"\nSample TARGETS ({len(targets)} total):")
    for c in targets[:5]:
        print(f"\n  {c.name}  [{c.trajectory_tag}]")
        for r in c.roles:
            dates = f"{r.start or '?'}-{r.end or 'present'}"
            print(f"    {r.title:<35} @ {r.company:<30} ({dates})")
            print(f"      key: {r.company_key}")

    print(f"\nSample BRIDGE pool ({len(bridges)} total):")
    for c in bridges[:3]:
        print(f"\n  {c.name}  [{c.trajectory_tag or 'no tag'}]")
        for r in c.roles:
            dates = f"{r.start or '?'}-{r.end or 'present'}"
            print(f"    {r.title:<35} @ {r.company:<30} ({dates})")
            print(f"      key: {r.company_key}")

    # ── Unique company keys across all contacts ───────────────────────────────
    all_keys = [r.company_key for c in contacts for r in c.roles]
    unique_keys = set(all_keys)
    print(f"\nTotal role entries  : {len(all_keys)}")
    print(f"Unique company keys : {len(unique_keys)}")
    print(f"Index size estimate : {len(unique_keys)} buckets")


if __name__ == "__main__":
    main()
