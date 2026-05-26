"""
Warm path parser — Layer 2.

Loads career_json records from Airtable and returns typed Contact objects
with normalized company keys ready for index building.

load_contacts(table) -> list[Contact]
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from backend.intelligence.warmpath.normalizer import normalize


@dataclass
class Role:
    title: str
    company: str        # raw name as scraped
    company_key: str    # normalize(company) — index key
    start: Optional[int]
    end: Optional[int]  # None = still there (present)


@dataclass
class Contact:
    record_id: str
    name: str
    trajectory_tag: str
    roles: list[Role] = field(default_factory=list)

    @property
    def is_tier1(self) -> bool:
        return self.trajectory_tag in ("EXITED_FOUNDER", "SERIAL_FOUNDER")

    @property
    def is_tier2(self) -> bool:
        return self.trajectory_tag in ("SENIOR_OPERATOR", "RSU_BENEFICIARY")

    @property
    def is_target(self) -> bool:
        return self.is_tier1 or self.is_tier2


def _parse_roles(career_json_str: str) -> list[Role]:
    """Parse a career_json string into Role objects. Returns [] on any error."""
    if not career_json_str:
        return []
    try:
        raw = json.loads(career_json_str)
    except (json.JSONDecodeError, TypeError):
        return []

    roles = []
    for entry in raw:
        company = (entry.get("company") or "").strip()
        if not company:
            continue
        key = normalize(company)
        if not key:
            continue  # noise name (self-employed etc.)
        roles.append(Role(
            title=       (entry.get("title") or "").strip(),
            company=     company,
            company_key= key,
            start=       entry.get("start"),   # int or None
            end=         entry.get("end"),      # int or None = present
        ))
    return roles


def load_contacts(table, tier_filter: Optional[str] = None) -> list[Contact]:
    """
    Fetch all contacts with career_json from an Airtable table object.

    Args:
        table: pyairtable Table instance
        tier_filter: if "targets", return only Tier 1+2 contacts;
                     if None, return all (used for bridge pool)

    Returns:
        list of Contact objects with parsed roles
    """
    records = table.all(
        fields=["career_json", "Name", "trajectory_tag"],
        formula="AND({career_json} != '', {career_json} != BLANK())",
    )

    contacts = []
    skipped_no_roles = 0

    for rec in records:
        f = rec["fields"]
        roles = _parse_roles(f.get("career_json", ""))
        if not roles:
            skipped_no_roles += 1
            continue

        c = Contact(
            record_id=     rec["id"],
            name=          (f.get("Name") or rec["id"]).strip(),
            trajectory_tag=(f.get("trajectory_tag") or "").strip(),
            roles=         roles,
        )

        if tier_filter == "targets" and not c.is_target:
            continue

        contacts.append(c)

    return contacts, skipped_no_roles
