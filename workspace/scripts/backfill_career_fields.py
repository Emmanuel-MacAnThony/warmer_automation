"""
Backfill last_three_roles, trajectory_tag, and career_json from all batch CSVs.
Creates the fields in Airtable if they don't exist, then writes all successfully
enriched records that have last_three_roles but are missing career_json.

Usage:
  python workspace/scripts/backfill_career_fields.py
  python workspace/scripts/backfill_career_fields.py --dry-run
"""

import argparse
import csv
import json
import re
import sys
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from pyairtable import Api
from backend.config import Config

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"   # fundraising_test_table
API_KEY  = Config.AIRTABLE_API_KEY

JOB2_CSVS = [
    "workspace/data/batches/job_2_batch_14.csv",
    "workspace/data/batches/job_2_batch_15.csv",
]

# handles en-dash (–), em-dash (—), hyphen (-), and the Windows-1252
# mangled variant (\x96 / \x9f) that shows up in some scraped text
DASH_RE = re.compile(r'[–—\-\x96\x9f]')

ROLE_RE = re.compile(
    r'^(.+?)\s+at\s+(.+?)\s*\((\d{4})?' + DASH_RE.pattern + r'(\d{4}|present)?\)\s*$',
    re.IGNORECASE,
)

FIELDS_TO_CREATE = [
    {"name": "last_three_roles", "type": "multilineText"},
    {"name": "trajectory_tag",   "type": "singleLineText"},
    {"name": "career_json",      "type": "multilineText"},
]


# ── Airtable helpers ────────────────────────────────────────────────────────

def get_table_id(base_id: str, table_name: str) -> str:
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    resp.raise_for_status()
    for t in resp.json().get("tables", []):
        if t["name"] == table_name or t["id"] == table_name:
            return t["id"]
    raise ValueError(f"Table '{table_name}' not found")


def ensure_fields(base_id: str, table_id: str, fields: list):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers=headers,
    )
    resp.raise_for_status()
    table_data  = next(t for t in resp.json()["tables"] if t["id"] == table_id)
    existing    = {f["name"] for f in table_data["fields"]}

    for field in fields:
        if field["name"] in existing:
            print(f"  field '{field['name']}' — already exists")
            continue
        r = requests.post(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields",
            headers=headers,
            json=field,
        )
        if r.status_code == 200:
            print(f"  field '{field['name']}' — created")
        else:
            print(f"  field '{field['name']}' — FAILED: {r.text}")


# ── career parser ───────────────────────────────────────────────────────────

def parse_roles(text: str) -> list:
    if not text:
        return []

    # normalise dashes before matching
    normalised = DASH_RE.sub("-", text)

    records = []
    for raw_line in normalised.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = re.match(
            r'^(.+?)\s+at\s+(.+?)\s*\((\d{4})?-(\d{4}|present)?\)\s*$',
            line,
            re.IGNORECASE,
        )
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
            company_raw   = parts[1].strip()
            company_clean = re.sub(r'\s*\([^)]*$', '', company_raw).strip()
            if company_clean:
                records.append({
                    "title":   parts[0].strip(),
                    "company": company_clean,
                    "start":   None,
                    "end":     None,
                })

    return records


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # ── load CSV data ──────────────────────────────────────────────────
    rows = []
    for path in JOB2_CSVS:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (
                    row.get("status") == "success"
                    and row.get("last_three_roles", "").strip()
                    and row.get("record_id", "").strip()
                ):
                    rows.append(row)

    print(f"Records from job_2 CSVs with last_three_roles: {len(rows)}")

    # ── parse career_json ──────────────────────────────────────────────
    full = partial = no_dates = 0
    updates = []

    for row in rows:
        parsed = parse_roles(row["last_three_roles"])
        if not parsed:
            continue

        starts = [r["start"] for r in parsed]
        if all(s is not None for s in starts):
            full += 1
        elif any(s is not None for s in starts):
            partial += 1
        else:
            no_dates += 1

        updates.append({
            "id": row["record_id"],
            "fields": {
                "last_three_roles": row["last_three_roles"].strip(),
                "trajectory_tag":   row.get("trajectory_tag", "").strip(),
                "career_json":      json.dumps(parsed, ensure_ascii=False),
            },
        })

    # ── report ─────────────────────────────────────────────────────────
    print()
    print("=" * 56)
    print("  PARSE REPORT")
    print("=" * 56)
    print(f"  Total records           : {len(rows)}")
    print(f"  Full dates (all roles)  : {full}")
    print(f"  Partial dates           : {partial}")
    print(f"  No dates (company only) : {no_dates}")
    print(f"  Ready to write          : {len(updates)}")
    print("=" * 56)

    # show 3 samples
    print("\nSamples:")
    for u in updates[:3]:
        fields = u["fields"]
        print(f"\n  {u['id']}")
        print(f"  trajectory_tag   : {fields['trajectory_tag']}")
        print(f"  last_three_roles : {repr(fields['last_three_roles'][:120])}")
        print(f"  career_json      : {fields['career_json'][:120]}")

    if args.dry_run:
        print("\n[DRY RUN] — nothing written")
        return

    # ── create fields + write ──────────────────────────────────────────
    print(f"\nTable ID: {TABLE_ID}")

    print("\nEnsuring fields exist...")
    ensure_fields(BASE_ID, TABLE_ID, FIELDS_TO_CREATE)

    api   = Api(API_KEY)
    table = api.table(BASE_ID, TABLE_ID)

    print(f"\nWriting {len(updates)} records to Airtable...")
    written = errors = 0

    for i in range(0, len(updates), 10):
        chunk = updates[i: i + 10]
        try:
            table.batch_update(chunk, typecast=True)
            written += len(chunk)
            print(f"  {written}/{len(updates)}", end="\r")
            time.sleep(0.22)
        except Exception as e:
            errors += len(chunk)
            print(f"\n  chunk {i // 10 + 1} failed: {e}")

    print(f"\nDone — {written} written  |  {errors} errors")


if __name__ == "__main__":
    main()
