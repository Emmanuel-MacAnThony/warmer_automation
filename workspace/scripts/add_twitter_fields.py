"""
Adds the 7 Twitter/X intelligence fields to the CRM table via Airtable Metadata API.
Skips fields that already exist. Safe to re-run.
"""
import sys, os, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyairtable import Api
from backend.config import Config

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"  # fundraising_test_table
HEADERS  = {
    "Authorization": f"Bearer {Config.AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

FIELDS_TO_CREATE = [
    {
        "name": "tweet_wealth_signal",
        "type": "multilineText",
    },
    {
        "name": "tweet_giving_signal",
        "type": "multilineText",
    },
    {
        "name": "tweet_topic_themes",
        "type": "multipleSelects",
        "options": {"choices": []},
    },
    {
        "name": "tweet_engagement_tier",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "High",   "color": "greenLight2"},
                {"name": "Medium", "color": "yellowLight2"},
                {"name": "Low",    "color": "grayLight2"},
            ]
        },
    },
    {
        "name": "tweet_personality_type",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "thought_leader",  "color": "blueLight2"},
                {"name": "curator",         "color": "purpleLight2"},
                {"name": "self_promoter",   "color": "orangeLight2"},
                {"name": "passive",         "color": "grayLight2"},
            ]
        },
    },
    {
        "name": "tweet_last_active",
        "type": "singleLineText",
    },
    {
        "name": "tweet_analyzed_links",
        "type": "multilineText",
    },
]


def get_existing_field_names() -> set:
    api = Api(Config.AIRTABLE_API_KEY)
    schema = api.base(BASE_ID).schema()
    table = next((t for t in schema.tables if t.id == TABLE_ID), None)
    if not table:
        raise ValueError(f"Table {TABLE_ID} not found")
    return {f.name for f in table.fields}


def create_field(field_def: dict) -> bool:
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields"
    resp = requests.post(url, headers=HEADERS, json=field_def)
    if resp.status_code == 200:
        created = resp.json()
        print(f"  created  '{created['name']}' (id={created['id']}, type={created['type']})")
        return True
    else:
        print(f"  FAILED   '{field_def['name']}': {resp.status_code} {resp.text}")
        return False


if __name__ == "__main__":
    print(f"Adding Twitter/X intelligence fields to: fundraising_test_table\n")

    existing = get_existing_field_names()
    print(f"Existing fields in table: {len(existing)}\n")

    created, skipped, failed = 0, 0, 0

    for field in FIELDS_TO_CREATE:
        if field["name"] in existing:
            print(f"  skipped  '{field['name']}' (already exists)")
            skipped += 1
        else:
            ok = create_field(field)
            if ok:
                created += 1
            else:
                failed += 1

    print(f"\nDone. created={created}  skipped={skipped}  failed={failed}")
