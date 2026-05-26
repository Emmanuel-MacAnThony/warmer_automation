"""
Test the company name normalizer against real career_json data from Airtable.

Pulls 104 enriched records from fundraising_test_table, extracts all company
names, normalizes them, and groups by normalized value to show clustering.

Usage:
  python workspace/scripts/test_normalizer.py
  python workspace/scripts/test_normalizer.py --min-cluster 2   # only show clusters of 2+
  python workspace/scripts/test_normalizer.py --show-all        # include singletons
"""

import argparse
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parents[2]))

from pyairtable import Api
from backend.config import Config
from backend.intelligence.warmpath.normalizer import normalize

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"   # fundraising_test_table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-cluster", type=int, default=2,
                    help="Minimum cluster size to display (default: 2)")
    ap.add_argument("--show-all", action="store_true",
                    help="Show all normalized names including singletons")
    args = ap.parse_args()

    min_size = 1 if args.show_all else args.min_cluster

    print(f"Fetching career_json from {TABLE_ID}...")
    api   = Api(Config.AIRTABLE_API_KEY)
    table = api.table(BASE_ID, TABLE_ID)

    records = table.all(
        fields=["career_json", "Name"],
        formula="AND({career_json} != '', {career_json} != BLANK())",
    )
    print(f"Fetched {len(records)} records with career_json\n")

    # raw_name → (normalized, [contact_names])
    # cluster map: normalized_key → list of (raw_name, contact_name)
    clusters: dict[str, list[tuple[str, str]]] = defaultdict(list)
    raw_to_norm: dict[str, str] = {}

    parse_errors = 0
    total_roles  = 0

    for rec in records:
        contact_name = rec["fields"].get("Name", rec["id"])
        raw_json     = rec["fields"].get("career_json", "")
        try:
            roles = json.loads(raw_json)
        except json.JSONDecodeError:
            parse_errors += 1
            continue

        for role in roles:
            company = role.get("company", "").strip()
            if not company:
                continue
            total_roles += 1
            norm = normalize(company)
            if norm:
                clusters[norm].append((company, contact_name))
                raw_to_norm[company] = norm

    print(f"Total role entries : {total_roles}")
    print(f"Unique normalized  : {len(clusters)}")
    print(f"Parse errors       : {parse_errors}")

    # clusters with 2+ raw entries
    multi = {k: v for k, v in clusters.items() if len(v) >= min_size}
    print(f"Clusters size >= {min_size}: {len(multi)}")
    print()

    # ── Normalization spot-check ────────────────────────────────────────────
    print("=" * 70)
    print("  NORMALIZATION SPOT-CHECK  (raw -> normalized)")
    print("=" * 70)

    # pick one unique raw name per normalized key, alphabetical
    seen_raw: set[str] = set()
    spot = []
    for norm, entries in sorted(clusters.items()):
        for raw, _ in entries:
            if raw not in seen_raw:
                seen_raw.add(raw)
                if raw.lower() != norm:   # only show where transform happened
                    spot.append((raw, norm))
                break

    spot.sort(key=lambda x: x[1])
    for raw, norm in spot[:60]:
        print(f"  {raw:<45} ->  {norm}")

    # ── Cluster report ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"  CLUSTERS  (normalized key, size >= {min_size})")
    print("=" * 70)

    sorted_clusters = sorted(multi.items(), key=lambda x: len(x[1]), reverse=True)

    for norm_key, entries in sorted_clusters:
        # deduplicate by raw name, count occurrences
        raw_counts: dict[str, int] = defaultdict(int)
        raw_contacts: dict[str, list[str]] = defaultdict(list)
        for raw, contact in entries:
            raw_counts[raw] += 1
            raw_contacts[raw].append(contact)

        total = len(entries)
        unique_contacts = len({c for _, c in entries})

        print(f"\n  [{norm_key}]  ({total} occurrences, {unique_contacts} contacts)")
        for raw, count in sorted(raw_counts.items(), key=lambda x: -x[1]):
            contacts_str = ", ".join(raw_contacts[raw][:3])
            if len(raw_contacts[raw]) > 3:
                contacts_str += f" +{len(raw_contacts[raw]) - 3} more"
            print(f"    {count}×  {raw:<40} ← {contacts_str}")

    # ── Summary ─────────────────────────────────────────────────────────────
    cluster_2plus = sum(1 for v in clusters.values() if len(v) >= 2)
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Records processed     : {len(records)}")
    print(f"  Total role entries    : {total_roles}")
    print(f"  Unique normalized     : {len(clusters)}")
    print(f"  Clusters with 2+ hits : {cluster_2plus}  ← potential warm path candidates")
    print(f"  Singletons            : {len(clusters) - cluster_2plus}")
    print("=" * 70)


if __name__ == "__main__":
    main()
