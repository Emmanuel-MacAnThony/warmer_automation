import requests, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyairtable import Api
from backend.config import Config

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"
HEADERS  = {"Authorization": f"Bearer {Config.AIRTABLE_API_KEY}", "Content-Type": "application/json"}

FIELDS = [
    {
        "name": "trajectory_tag",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "RSU_BENEFICIARY",       "color": "blueLight2"},
                {"name": "EARLY_EMPLOYEE",         "color": "greenLight2"},
                {"name": "SERIAL_EARLY_EMPLOYEE",  "color": "tealLight2"},
                {"name": "SERIAL_FOUNDER",         "color": "purpleLight2"},
                {"name": "SENIOR_OPERATOR",        "color": "yellowLight2"},
                {"name": "EXITED_FOUNDER",         "color": "orangeLight2"},
                {"name": "UNCLEAR",                "color": "grayLight2"},
            ]
        }
    },
    {
        "name": "trajectory_signal",
        "type": "multilineText",
    },
]

api      = Api(Config.AIRTABLE_API_KEY)
schema   = api.base(BASE_ID).schema()
table    = next(t for t in schema.tables if t.id == TABLE_ID)
existing = {f.name for f in table.fields}

for field in FIELDS:
    if field["name"] in existing:
        print(f"  skipped  '{field['name']}' (already exists)")
    else:
        resp = requests.post(
            f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields",
            headers=HEADERS,
            json=field
        )
        if resp.status_code == 200:
            r = resp.json()
            print(f"  created  '{r['name']}'  id={r['id']}  type={r['type']}")
        else:
            print(f"  FAILED   '{field['name']}': {resp.status_code} {resp.text}")
