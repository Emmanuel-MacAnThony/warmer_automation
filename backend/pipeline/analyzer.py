"""
Batch Analyzer — extract Airtable field values from a scraped LinkedIn profile.

Two classes:
- BatchAnalyzer      : calls LLM with profile data + field spec → raw extracted dict
- BatchOutputValidator: validates extracted values including singleSelect/multipleSelects
                        (the existing OutputValidator skips those — this one handles them)

field_mapping format stored on the job (keyed by Airtable field ID):
    {
        "fldXXX": {
            "airtable_name": "Industry",
            "airtable_type": "singleSelect",
            "canonical_key": "industry",      ← key to look for in apify_data
            "choices": ["Technology", "Finance", ...]
        },
        "fldYYY": {
            "airtable_name": "LinkedIn",
            "airtable_type": "url",
            "canonical_key": "linkedin_url",
            "choices": []
        }
    }
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.config import Config

logger = logging.getLogger(__name__)

# Shared semaphore — max 5 concurrent LLM calls across all jobs in the process
_llm_semaphore = asyncio.Semaphore(5)

# Profile intelligence fields always extracted regardless of the job's field mapping.
PROFILE_SIGNAL_FIELDS: Dict[str, str] = {
    "last_three_roles":   "multilineText",  # derived from experience data, no LLM
    "trajectory_tag":     "singleSelect",   # LLM classification — one of 6 archetypes below
    "trajectory_signal":  "multilineText",  # LLM plain-English explanation of the tag
}

# Career archetype definitions used in the LLM prompt and as the allowed singleSelect values.
# Add new archetypes here — they automatically appear in the prompt guidance.
TRAJECTORY_ARCHETYPES: Dict[str, str] = {
    "RSU_BENEFICIARY": (
        "Long tenure (4+ years) at a post-IPO tech/finance company in a senior IC or manager role. "
        "Wealth comes from vested stock that appreciated over time."
    ),
    "EARLY_EMPLOYEE": (
        "Joined a startup as one of the first ~50 employees before a major liquidity event "
        "(IPO or acquisition). Did it once. Tenure ended around or after the event."
    ),
    "SERIAL_EARLY_EMPLOYEE": (
        "Repeatedly joined companies early (non-founder, employee #5–50) across 2 or more startups. "
        "Pattern of identifying high-growth opportunities early and accumulating equity across multiple bets."
    ),
    "SERIAL_FOUNDER": (
        "Appears as founder or co-founder across 2 or more distinct companies in their career history."
    ),
    "SENIOR_OPERATOR": (
        "C-suite (CEO/COO/CTO/CFO/CMO) or VP-level title at one or more companies, "
        "never listed as founder. Wealth comes from salary, bonus, and executive equity packages."
    ),
    "EXITED_FOUNDER": (
        "Founded a company once, had a liquidity event (acquisition or IPO), "
        "and is now in a soft role: board member, advisor, angel investor, or venture partner."
    ),
    "UNCLEAR": (
        "Career history does not clearly fit any of the above archetypes, "
        "or there is insufficient data to classify confidently."
    ),
}


def extract_career_progression(apify_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract last_three_roles directly from the experience array.
    No LLM — pure data. Format per role: "Title at Company (start–end)"

    Handles both actor schemas:
      harvestapi: experience[].position, startDate.year, endDate.year
      dev_fusion: experiences[].title,   jobStartedOn,  jobEndedOn
    """
    raw = apify_data.get("raw_data") or {}
    experience = (
        raw.get("experience")
        or raw.get("experiences")
        or apify_data.get("experience")
        or []
    )

    roles = []
    for exp in experience[:3]:
        title   = exp.get("position") or exp.get("title") or ""
        company = exp.get("companyName") or exp.get("company") or ""

        # Date: harvestapi returns {"year": 2021, "month": 3} objects
        start_raw = exp.get("startDate") or {}
        end_raw   = exp.get("endDate")   or {}
        start = start_raw.get("year") if isinstance(start_raw, dict) else exp.get("jobStartedOn") or ""
        end   = end_raw.get("year")   if isinstance(end_raw, dict)   else exp.get("jobEndedOn")

        # A null endDate in harvestapi means the role is current
        if not end:
            end = "present"

        if title and company:
            roles.append(f"{title} at {company} ({start}–{end})")

    if not roles:
        return {}
    return {"last_three_roles": "\n".join(roles)}

# Field types that are read-only / computed — never write to these
_SKIP_TYPES = {
    "formula",
    "rollup",
    "count",
    "lookup",
    "createdTime",
    "lastModifiedTime",
    "createdBy",
    "lastModifiedBy",
    "autoNumber",
    "barcode",
    "button",
}


class BatchAnalyzer:
    """
    LLM-driven field extractor for batch enrichment.

    Uses field_mapping (keyed by field ID) to know:
    - Which Airtable fields to populate
    - Which LinkedIn data key to look for (canonical_key)
    - What the allowed choices are for select fields
    """

    def __init__(self):
        self._llm = ChatOpenAI(
            model=Config.OPENAI_MODEL,
            temperature=0.1,
            api_key=Config.OPENAI_API_KEY,
        )

    async def analyze(
        self,
        apify_data: Dict[str, Any],
        field_mapping: Dict,
    ) -> Dict[str, Any]:
        """
        Extract Airtable field values from LinkedIn profile data.

        Args:
            apify_data:    Structured profile from preserve_apify_data()
            field_mapping: Job mapping {fldXXX: {airtable_name, airtable_type,
                           canonical_key, choices}}

        Returns:
            Dict keyed by airtable_name — raw LLM output, not yet validated.
        """
        if not field_mapping:
            return {}

        # Build target fields list, skipping read-only types
        target_fields = [
            {
                "name": cfg["airtable_name"],
                "type": cfg["airtable_type"],
                "canonical_key": cfg["canonical_key"],
                "choices": cfg.get("choices", []),
            }
            for cfg in field_mapping.values()
            if cfg.get("airtable_type") not in _SKIP_TYPES
            and cfg.get("airtable_name")
            and cfg.get("canonical_key")
        ]

        if not target_fields:
            return {}

        prompt = self._build_prompt(apify_data, target_fields)

        async with _llm_semaphore:
            messages = [
                SystemMessage(
                    content=(
                        "You extract structured data from LinkedIn profiles for CRM enrichment. "
                        "Always respond with a valid JSON object only — no explanation, no markdown. "
                        "Only include fields you can confidently populate from the profile data."
                    )
                ),
                HumanMessage(content=prompt),
            ]
            response = await self._llm.ainvoke(messages)

        return self._parse_response(response.content)

    # Fields pulled from raw_data into the LLM prompt.
    # Lists both dev_fusion and harvestapi key names — whichever is present gets included.
    _RAW_INCLUDE = [
        # dev_fusion top-level computed fields
        "jobTitle", "companyName", "companyIndustry", "companyWebsite",
        "companyLinkedin", "companySize", "jobStartedOn", "jobLocation",
        "isCurrentlyEmployed", "totalExperienceYears", "experiencesCount",
        "firstRoleYear", "addressWithCountry", "addressCountryOnly",
        "isPremium", "isJobSeeker",
        # harvestapi equivalents / additions
        "currentPosition",   # [{position, companyName, companyLinkedinUrl, startDate, ...}]
        "experience",        # full career array (harvestapi key; dev_fusion uses 'experiences')
        "experiences",       # dev_fusion career array
        "education",         # harvestapi key
        "educations",        # dev_fusion key
        "topSkills",         # harvestapi only
        "skills",
        "followerCount",     # harvestapi
        "connectionsCount",  # harvestapi
        "openToWork",        # harvestapi
        "premium",           # harvestapi
        "causes",            # harvestapi only — publicly listed causes (philanthropy signal)
    ]

    def _build_prompt(self, apify_data: Dict, target_fields: List[Dict]) -> str:
        raw = apify_data.get("raw_data") or {}

        # Structured top-level fields (exclude raw blobs — posts handled separately)
        _EXCLUDE = {"raw_data", "posts"}
        profile = {
            k: v for k, v in apify_data.items()
            if k not in _EXCLUDE and v not in (None, "", [])
        }

        # Merge in key Apify-computed fields that live only in raw_data
        raw_extra = {
            k: raw[k] for k in self._RAW_INCLUDE
            if raw.get(k) not in (None, "", [])
        }
        profile.update(raw_extra)

        field_lines = []
        for f in target_fields:
            line = f'- "{f["name"]}" (type: {f["type"]}, look for: {f["canonical_key"]}'
            if f["choices"]:
                line += f', allowed values: {json.dumps(f["choices"])}'
            line += ")"
            field_lines.append(line)

        archetype_lines = "\n".join(
            f'  "{tag}": {desc}' for tag, desc in TRAJECTORY_ARCHETYPES.items()
        )

        return (
            f"LinkedIn profile data:\n{json.dumps(profile, indent=2, default=str)}\n\n"
            f"Extract these Airtable CRM fields:\n"
            + "\n".join(field_lines)
            + "\n\nExtraction rules:\n"
            "- Career data comes from 'experience' (harvestapi) or 'experiences' (dev_fusion) — use whichever is present.\n"
            "  harvestapi entry shape: {position, companyName, companyLinkedinUrl, startDate, endDate, duration, description, skills}\n"
            "  dev_fusion entry shape: {title, companyName, companyIndustry, jobStartedOn, jobEndedOn, jobStillWorking}\n"
            "  • last_three_companies: join the 3 most recent companyName values, comma-separated.\n"
            "  • company_industry: use companyIndustry if present, else infer from headline or description.\n"
            "  • total_experience_years: use totalExperienceYears if present, else estimate from date ranges.\n"
            "  • job title: use 'position' (harvestapi) or 'title' (dev_fusion).\n"
            "- 'currentPosition' (harvestapi only) is a pre-extracted array of current roles — use it as the primary source for current company and title.\n"
            "- Education: 'education' (harvestapi) or 'educations' (dev_fusion). harvestapi entry has 'schoolName' and 'degreeName'; dev_fusion has 'title' (school) and 'subtitle' (degree).\n"
            "- 'causes' (harvestapi only): publicly listed causes this person supports — strong philanthropy signal.\n"
            "- Be creative: synthesize derived fields from arrays "
            "(e.g., last 3 companies from experiences, industry from headline/role).\n"
            "- For summary/about fields: write 2-4 insightful sentences a fundraiser would find valuable.\n"
            "- singleSelect: return exactly one string from allowed values, or omit if none fits.\n"
            "- multipleSelects: return a JSON array of strings from allowed values.\n"
            "- text/url: return a concise string.\n"
            "- Omit fields you cannot confidently populate.\n"
            "\nAlways also extract these two trajectory fields (in addition to the fields above):\n"
            '- "trajectory_tag": classify this person into exactly one of the following archetypes based on their full career history:\n'
            + archetype_lines + "\n"
            '- "trajectory_signal": one sentence explaining WHY you assigned that tag. '
            "Reference specific roles, companies, or dates from the career history.\n"
            '- Respond with ONLY a JSON object: {"Airtable Field Name": value, ...}'
        )

    def _parse_response(self, content: str) -> Dict[str, Any]:
        try:
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            data = json.loads(content.strip())
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as err:
            logger.warning("BatchAnalyzer: failed to parse LLM JSON response", err)
            return {}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class BatchOutputValidator:
    """
    Validates LLM-extracted fields against the field_mapping.

    Key difference from OutputValidator: handles singleSelect and multipleSelects
    by checking values against the choices list already in the field_mapping.
    """

    def validate(
        self,
        extracted: Dict[str, Any],
        field_mapping: Dict,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Returns (validated_fields, errors).
        validated_fields: safe to write directly to Airtable (keyed by airtable_name).
        """
        # Build lookup by airtable_name → field config
        by_name = {cfg["airtable_name"]: cfg for cfg in field_mapping.values()}

        validated: Dict[str, Any] = {}
        errors: List[str] = []

        for field_name, value in extracted.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue

            cfg = by_name.get(field_name)
            if not cfg:
                errors.append(f"Unknown field: {field_name}")
                continue

            field_type = cfg.get("airtable_type", "")
            if field_type in _SKIP_TYPES:
                errors.append(f"Read-only field skipped: {field_name}")
                continue

            try:
                validated[field_name] = self._coerce(
                    value, field_type, cfg.get("choices", [])
                )
            except ValueError as e:
                errors.append(f"{field_name}: {e}")

        return validated, errors

    def _coerce(self, value: Any, field_type: str, choices: List[str]) -> Any:
        if field_type == "singleSelect":
            value_str = str(value).strip()
            if choices:
                match = next(
                    (c for c in choices if c.lower() == value_str.lower()), None
                )
                if not match:
                    raise ValueError(f"'{value_str}' not in allowed choices: {choices}")
                return match
            return value_str

        elif field_type == "multipleSelects":
            items = value if isinstance(value, list) else [value]
            result = []
            for item in items:
                item_str = str(item).strip()
                if choices:
                    match = next(
                        (c for c in choices if c.lower() == item_str.lower()), None
                    )
                    if match:
                        result.append(match)
                    else:
                        logger.debug(
                            f"multipleSelects: '{item_str}' not in choices, skipping"
                        )
                else:
                    result.append(item_str)
            if not result:
                raise ValueError("No valid choices matched")
            return result

        elif field_type == "number":
            try:
                return float(value)
            except (ValueError, TypeError):
                raise ValueError(f"Cannot convert to number: {value}")

        elif field_type == "checkbox":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1")
            raise ValueError(f"Cannot convert to checkbox: {value}")

        elif field_type in ("date", "dateTime"):
            if not isinstance(value, str):
                raise ValueError("Date must be a string")
            return value

        else:
            # singleLineText, multilineText, url, email, phoneNumber, unknown
            if isinstance(value, list):
                value = value[0] if len(value) == 1 else ", ".join(str(v) for v in value)
            return str(value).strip()
