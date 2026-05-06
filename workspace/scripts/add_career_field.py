import requests, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyairtable import Api
from backend.config import Config

BASE_ID  = Config.AIRTABLE_BASE_ID
TABLE_ID = "tblJ0JMa1VxSLBHa7"
HEADERS  = {"Authorization": f"Bearer {Config.AIRTABLE_API_KEY}", "Content-Type": "application/json"}

api    = Api(Config.AIRTABLE_API_KEY)
schema = api.base(BASE_ID).schema()
table  = next(t for t in schema.tables if t.id == TABLE_ID)
existing = {f.name for f in table.fields}

if "last_three_roles" in existing:
    print("last_three_roles already exists — skipped")
else:
    resp = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields",
        headers=HEADERS,
        json={"name": "last_three_roles", "type": "multilineText"}
    )
    if resp.status_code == 200:
        r = resp.json()
        print(f"Created last_three_roles  id={r['id']}")
    else:
        print(f"FAILED: {resp.status_code} {resp.text}")
