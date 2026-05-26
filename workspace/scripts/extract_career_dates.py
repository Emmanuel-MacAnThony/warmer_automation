"""
Extract structured career data from last_three_roles and write career_json
back to Airtable. Auto-creates the career_json field if it doesn't exist.

Usage:
  python workspace/scripts/extract_career_dates.py
  python workspace/scripts/extract_career_dates.py --dry-run
  python workspace/scripts/extract_career_dates.py --limit 50
  python workspace/scripts/extract_career_dates.py --base-id appXXX --table-name "My Table"
"""

import argparse
import json
import re
import sys
import time
import logging
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from pyairtable import Api
from backend.config import Config

# ── constants ──────────────────────────────────────────────────────────────

SOURCE_FIELD = "last_three_roles"
TARGET_FIELD = "career_json"

ROLE_RE = re.compile(
    r'^(.+?)\s+at\s+(.+?)\s*\((\d{4})?[–\-—](\d{4}|present)?\)\s*$',
    re.IGNORECASE,
)


# ── field creation ─────────────────────────────────────────────────────────

def ensure_field_exists(api_key: str, base_id: str, table_id: str, field_name: str) -> bool:
    """Create field if it doesn't exist. Returns True if ready."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # check existing fields
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers=headers,
    )
    resp.raise_for_status()

    table_data = next(
        (t for t in resp.json().get("tables", []) if t["id"] == table_id),
        None,
    )
    if not table_data:
        print(f"  Table {table_id} not found in schema response")
        return False

    existing = [f["name"] for f in table_data.get("fields", [])]
    if field_name in existing:
        print(f"  Field '{field_name}' already exists")
        return True

    # create it
    print(f"  Creating field '{field_name}'...")
    create_resp = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields",
        headers=headers,
        json={"name": field_name, "type": "multilineText"},
    )
    if create_resp.status_code == 200:
        print(f"  Field '{field_name}' created")
        return True
    else:
        print(f"  Could not auto-create field: {create_resp.text}")
        print(f"  Create it manually in Airtable as a Long Text field named '{field_name}'")
        return False


def get_table_id(api_key: str, base_id: str, table_name: str) -> str:
    """Resolve table name → table ID."""
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers=headers,
    )
    resp.raise_for_status()
    for t in resp.json().get("tables", []):
        if t["name"] == table_name or t["id"] == table_name:
            return t["id"]
    raise ValueError(f"Table '{table_name}' not found in base {base_id}")


# ── parser ─────────────────────────────────────────────────────────────────

def parse_roles(text: str) -> list:
    if not text:
        return []

    records = []
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = ROLE_RE.match(line)
        if m:
            title, company, start_raw, end_raw = m.groups()
            start = int(start_raw) if start_raw else None
            end   = None if (not end_raw or end_raw.lower() == "present") else int(end_raw)
            records.append({
                "title":   title.strip(),
                "company": company.strip(),
                "start":   start,
                "end":     end,
            })
        elif " at " in line.lower():
            parts = re.split(r'\s+at\s+', line, maxsplit=1, flags=re.IGNORECASE)
            title       = parts[0].strip()
            company_raw = parts[1].strip()
            company_clean = re.sub(r'\s*\([^)]*$', '', company_raw).strip()
            if company_clean:
                records.append({
                    "title":   title,
                    "company": company_clean,
                    "start":   None,
                    "end":     None,
                })

    return records


def classify(parsed: list) -> str:
    if not parsed:
        return "unparsed"
    starts = [r["start"] for r in parsed]
    if all(s is not None for s in starts):
        return "full"
    if any(s is not None for s in starts):
        return "partial"
    return "none"


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-id",    default=Config.AIRTABLE_BASE_ID)
    ap.add_argument("--table-name", default=Config.AIRTABLE_TABLE_NAME)
    ap.add_argument("--dry-run",    action="store_true")
    ap.add_argument("--limit",      type=int, default=None)
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    print(f"Base  : {args.base_id}")
    print(f"Table : {args.table_name}")

    # resolve table name → ID
    print("\nResolving table ID...")
    table_id = get_table_id(Config.AIRTABLE_API_KEY, args.base_id, args.table_name)
    print(f"Table ID: {table_id}")

    # ensure career_json field exists
    print(f"\nChecking '{TARGET_FIELD}' field...")
    if not args.dry_run:
        ensure_field_exists(Config.AIRTABLE_API_KEY, args.base_id, table_id, TARGET_FIELD)

    # fetch records
    api   = Api(Config.AIRTABLE_API_KEY)
    table = api.table(args.base_id, table_id)

    print(f"\nFetching records with '{SOURCE_FIELD}' populated...")
    records = table.all(
        fields=[SOURCE_FIELD, "Name", "trajectory_tag"],
        formula=f"AND({{{SOURCE_FIELD}}} != '', {{{SOURCE_FIELD}}} != BLANK())",
    )

    if args.limit:
        records = records[: args.limit]

    total = len(records)
    print(f"Fetched {total} records\n")

    if total == 0:
        print("Nothing to process.")
        return

    # parse
    counts   = {"full": 0, "partial": 0, "none": 0, "unparsed": 0}
    samples  = {"full": [], "partial": [], "none": [], "unparsed": []}
    to_write = []

    for rec in records:
        fields     = rec["fields"]
        roles_text = fields.get(SOURCE_FIELD, "")
        parsed     = parse_roles(roles_text)
        bucket     = classify(parsed)

        counts[bucket] += 1
        if len(samples[bucket]) < 2:
            samples[bucket].append({
                "name":   fields.get("Name", rec["id"]),
                "raw":    roles_text,
                "parsed": parsed,
            })

        if parsed:
            to_write.append({
                "id":     rec["id"],
                "fields": {TARGET_FIELD: json.dumps(parsed, ensure_ascii=False)},
            })

    # report
    print("=" * 62)
    print("  CAREER DATE EXTRACTION REPORT")
    print("=" * 62)
    print(f"  Total records processed   : {total}")
    print(f"  Full dates  (all roles)   : {counts['full']:>5}  ({counts['full']/total*100:5.1f}%)")
    print(f"  Partial dates             : {counts['partial']:>5}  ({counts['partial']/total*100:5.1f}%)")
    print(f"  Company only  (no dates)  : {counts['none']:>5}  ({counts['none']/total*100:5.1f}%)")
    print(f"  Could not parse           : {counts['unparsed']:>5}  ({counts['unparsed']/total*100:5.1f}%)")
    print(f"\n  Records ready to write    : {len(to_write)}")
    print("=" * 62)

    for bucket, label in [
        ("full",     "FULL DATES"),
        ("partial",  "PARTIAL DATES"),
        ("none",     "NO DATES — company only"),
        ("unparsed", "COULD NOT PARSE"),
    ]:
        if not samples[bucket]:
            continue
        print(f"\n── {label} ──")
        for s in samples[bucket]:
            print(f"  {s['name']}")
            print(f"    raw    : {repr(s['raw'][:120])}")
            print(f"    parsed : {s['parsed']}")

    if args.dry_run:
        print("\n[DRY RUN] — nothing written to Airtable")
        return

    if not to_write:
        print("\nNothing to write.")
        return

    # write
    print(f"\nWriting to Airtable ({len(to_write)} records)...")
    written = 0
    errors  = 0

    for i in range(0, len(to_write), 10):
        chunk = to_write[i: i + 10]
        try:
            table.batch_update(chunk, typecast=True)
            written += len(chunk)
            print(f"  {written}/{len(to_write)}", end="\r")
            time.sleep(0.22)
        except Exception as e:
            errors += len(chunk)
            print(f"\n  chunk {i // 10 + 1} failed: {e}")

    print(f"\nDone — {written} written  |  {errors} errors")


if __name__ == "__main__":
    main()
