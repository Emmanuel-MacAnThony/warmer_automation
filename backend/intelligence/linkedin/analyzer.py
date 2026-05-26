"""
LinkedIn Intelligence Analyzer

Two concerns, one file:

PROFILE ANALYSIS — extract Airtable field values and career trajectory from
a scraped LinkedIn profile via LLM (BatchAnalyzer) plus pure-data career
progression extraction (extract_career_progression).

POSTS ANALYSIS — extract 7 fundraising signals from a person's LinkedIn posts
via a pre-filter → LLM → metadata pipeline (extract_post_signals).
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.config import Config
from backend.infra.llm import LLMProvider
from backend.intelligence.shared.keywords import (
    GIVING_SIGNAL_TERMS,
    PERSONALITY_TYPES,
    WEALTH_SIGNAL_TERMS,
)

logger = logging.getLogger(__name__)

# Shared semaphore — max 5 concurrent LLM calls across all jobs in the process
_llm_semaphore = asyncio.Semaphore(5)

# Field types that are read-only / computed — never write to these
_SKIP_TYPES = {
    "formula", "rollup", "count", "lookup",
    "createdTime", "lastModifiedTime", "createdBy", "lastModifiedBy",
    "autoNumber", "barcode", "button",
}


# ---------------------------------------------------------------------------
# Fixed LLM output fields — exactly the 25 Airtable columns BatchAnalyzer
# populates (derived from the existing DB mapping; "LinkedIn" input and
# "Last email sent" date field are excluded — they are never LLM-written).
# Auto-created in user's table via ensure_table_fields on first job run.
# ---------------------------------------------------------------------------

FIXED_LLM_OUTPUT_FIELDS: List[Dict[str, Any]] = [
    # identity
    {"name": "Name",                          "type": "multilineText",  "canonical_key": "full_name",        "choices": []},
    {"name": "First Name",                    "type": "singleLineText", "canonical_key": "first_name",       "choices": []},
    {"name": "Last Name",                     "type": "singleLineText", "canonical_key": "last_name",        "choices": []},
    # contact
    {"name": "Email",                         "type": "email",          "canonical_key": "email",            "choices": []},
    {"name": "Batch (Email)",                 "type": "singleLineText", "canonical_key": "email",            "choices": []},
    {"name": "Twitter",                       "type": "url",            "canonical_key": "twitter",          "choices": []},
    {"name": "Website",                       "type": "url",            "canonical_key": "website",          "choices": []},
    # location
    {"name": "Realtime location",             "type": "multilineText",  "canonical_key": "location",         "choices": []},
    {"name": "City",                          "type": "multipleSelects","canonical_key": "city",             "choices": []},
    {"name": "Wealthy Capacity/Networth",     "type": "multipleSelects","canonical_key": "city",             "choices": []},
    {"name": "Region",                        "type": "singleLineText", "canonical_key": "state",            "choices": []},
    {"name": "State/Emirate",                 "type": "multipleSelects","canonical_key": "state",            "choices": []},
    {"name": "Country",                       "type": "multipleSelects","canonical_key": "country",          "choices": []},
    # current role
    {"name": "Realtime role",                 "type": "multilineText",  "canonical_key": "job_title",        "choices": []},
    {"name": "Job Title",                     "type": "singleLineText", "canonical_key": "job_title",        "choices": []},
    {"name": "Realtime company name",         "type": "multilineText",  "canonical_key": "company_name",     "choices": []},
    {"name": "Company Name",                  "type": "multilineText",  "canonical_key": "company_name",     "choices": []},
    {"name": "Realtime company industry",     "type": "multilineText",  "canonical_key": "company_industry", "choices": []},
    {"name": "Industry",                      "type": "multipleSelects","canonical_key": "company_industry", "choices": []},
    {"name": "Realtime company link",         "type": "multilineText",  "canonical_key": "company_website",  "choices": []},
    {"name": "Company Website",               "type": "multilineText",  "canonical_key": "company_website",  "choices": []},
    # career / experiences
    {"name": "Realtime last 3 companies",     "type": "multilineText",  "canonical_key": "experiences",      "choices": []},
    {"name": "Realtime last 3 industries",    "type": "multilineText",  "canonical_key": "experiences",      "choices": []},
    {"name": "Tags",                          "type": "multipleSelects","canonical_key": "experiences",      "choices": []},
    # education
    {"name": "BC Linkedin Connection Degree", "type": "multipleSelects","canonical_key": "degree",           "choices": []},
]

# Lookup by airtable name — used by BatchOutputValidator
_FIXED_BY_NAME: Dict[str, Dict[str, Any]] = {f["name"]: f for f in FIXED_LLM_OUTPUT_FIELDS}


# ---------------------------------------------------------------------------
# Field registries — used by executor for CSV headers and Airtable flush type map
# ---------------------------------------------------------------------------

PROFILE_SIGNAL_FIELDS: Dict[str, str] = {
    "last_three_roles":  "multilineText",
    "career_json":       "multilineText",
    "trajectory_tag":    "singleSelect",
    "trajectory_signal": "multilineText",
    # One concrete, true sentence a fundraiser can open a personal email with.
    # Resolved per-contact via the [personalization_hook] template slot.
    "personalization_hook": "multilineText",
}

POST_SIGNAL_FIELDS: Dict[str, str] = {
    "post_wealth_signal":    "multilineText",
    "post_giving_signal":    "multilineText",
    "post_topic_themes":     "multipleSelects",
    "post_engagement_tier":  "singleSelect",
    "post_personality_type": "singleSelect",
    "post_last_active":      "singleLineText",
    "post_analyzed_links":   "multilineText",
}


# ---------------------------------------------------------------------------
# Career trajectory archetypes
# ---------------------------------------------------------------------------

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

# Engagement thresholds for post_engagement_tier (calibrated for professional LinkedIn audience)
ENGAGEMENT_THRESHOLDS = {
    "High":   100,
    "Medium":  20,
    "Low":      0,
}


# ===========================================================================
# PROFILE ANALYSIS
# ===========================================================================

def _extract_year(val) -> Optional[int]:
    """Parse a year from int, dict with 'year' key, or date string like '2018-03'."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, dict):
        return val.get("year")
    try:
        return int(str(val).strip()[:4])
    except (ValueError, IndexError):
        return None


def extract_career_progression(apify_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract career data from the experience array. No LLM — pure data.

    Returns:
      last_three_roles — human-readable text for display
      career_json      — structured JSON string of all roles for warm path matching

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

    all_roles = []
    for exp in experience:
        title   = (exp.get("position") or exp.get("title") or "").strip()
        company = (exp.get("companyName") or exp.get("company") or "").strip()
        if not title or not company:
            continue

        start = _extract_year(exp.get("startDate") or exp.get("jobStartedOn"))
        end   = _extract_year(exp.get("endDate")   or exp.get("jobEndedOn"))

        all_roles.append({"title": title, "company": company, "start": start, "end": end})

    if not all_roles:
        return {}

    display_lines = [
        f"{r['title']} at {r['company']} ({r['start'] or ''}–{r['end'] or 'present'})"
        for r in all_roles[:3]
    ]

    return {
        "last_three_roles": "\n".join(display_lines),
        "career_json":      json.dumps(all_roles),
    }


class BatchAnalyzer:
    """
    LLM-driven field extractor for batch enrichment.

    Uses field_mapping (keyed by field ID) to know which Airtable fields to
    populate, which LinkedIn data key to look for, and what the allowed
    choices are for select fields.
    """

    # Fields pulled from raw_data into the LLM prompt.
    # Lists both dev_fusion and harvestapi key names — whichever is present gets included.
    _RAW_INCLUDE = [
        "jobTitle", "companyName", "companyIndustry", "companyWebsite",
        "companyLinkedin", "companySize", "jobStartedOn", "jobLocation",
        "isCurrentlyEmployed", "totalExperienceYears", "experiencesCount",
        "firstRoleYear", "addressWithCountry", "addressCountryOnly",
        "isPremium", "isJobSeeker",
        "currentPosition", "experience", "experiences",
        "education", "educations",
        "topSkills", "skills",
        "followerCount", "connectionsCount",
        "openToWork", "premium",
        "causes",
    ]

    def __init__(self, provider: LLMProvider | None = None):
        if provider is None:
            from backend.infra.llm.factory import get_llm_provider
            provider = get_llm_provider()
        self._provider = provider

    async def analyze(self, apify_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract Airtable field values from LinkedIn profile data.
        Returns dict keyed by airtable_name — raw LLM output, not yet validated.
        """
        target_fields = [
            {
                "name":          f["name"],
                "type":          f["type"],
                "canonical_key": f["canonical_key"],
                "choices":       f.get("choices", []),
            }
            for f in FIXED_LLM_OUTPUT_FIELDS
            if f.get("type") not in _SKIP_TYPES and f.get("canonical_key")
        ]

        prompt = self._build_prompt(apify_data, target_fields)

        messages = [
            {"role": "system", "content": (
                "You extract structured data from LinkedIn profiles for CRM enrichment. "
                "Always respond with a valid JSON object only — no explanation, no markdown. "
                "Only include fields you can confidently populate from the profile data."
            )},
            {"role": "user", "content": prompt},
        ]
        async with _llm_semaphore:
            result = await self._provider.complete(messages, model=Config.OPENAI_MODEL, temperature=0.1)

        return _parse(result)

    def _build_prompt(self, apify_data: Dict, target_fields: List[Dict]) -> str:
        raw = apify_data.get("raw_data") or {}

        _EXCLUDE = {"raw_data", "posts"}
        profile = {k: v for k, v in apify_data.items() if k not in _EXCLUDE and v not in (None, "", [])}
        raw_extra = {k: raw[k] for k in self._RAW_INCLUDE if raw.get(k) not in (None, "", [])}
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
            "- Be creative: synthesize derived fields from arrays (e.g., last 3 companies from experiences, industry from headline/role).\n"
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


class BatchOutputValidator:
    """
    Validates LLM-extracted fields against the field_mapping.
    Handles singleSelect and multipleSelects by checking values against
    the choices list in the field_mapping.
    """

    def validate(
        self, extracted: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Returns (validated_fields, errors). validated_fields is safe to write to Airtable."""
        validated: Dict[str, Any] = {}
        errors: List[str] = []

        for field_name, value in extracted.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue

            cfg = _FIXED_BY_NAME.get(field_name)
            if not cfg:
                errors.append(f"Unknown field: {field_name}")
                continue

            field_type = cfg.get("type", "")
            if field_type in _SKIP_TYPES:
                errors.append(f"Read-only field skipped: {field_name}")
                continue

            try:
                validated[field_name] = self._coerce(value, field_type, cfg.get("choices", []))
            except ValueError as e:
                errors.append(f"{field_name}: {e}")

        return validated, errors

    def _coerce(self, value: Any, field_type: str, choices: List[str]) -> Any:
        if field_type == "singleSelect":
            value_str = str(value).strip()
            if choices:
                match = next((c for c in choices if c.lower() == value_str.lower()), None)
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
                    match = next((c for c in choices if c.lower() == item_str.lower()), None)
                    if match:
                        result.append(match)
                    else:
                        logger.debug(f"multipleSelects: '{item_str}' not in choices, skipping")
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
            if isinstance(value, list):
                value = value[0] if len(value) == 1 else ", ".join(str(v) for v in value)
            return str(value).strip()


# ===========================================================================
# POSTS ANALYSIS
# ===========================================================================

def pre_filter_posts(posts: List[Dict]) -> List[Dict]:
    """
    Score each post by fundraising signal value and return the top subset.
    Returns up to 13 posts: top 10 by score + 3 most recent (deduplicated).
    """
    for post in posts:
        engagement  = post.get("engagement") or {}
        likes       = engagement.get("likes", 0)    or 0
        comments    = engagement.get("comments", 0) or 0
        shares      = engagement.get("shares", 0)   or 0
        is_original = 1 if post.get("type") == "post" else 0

        post["_signal_score"] = (
            likes    * 1 +
            comments * 3 +
            shares   * 2 +
            is_original * 10
        )

    by_score  = sorted(posts, key=lambda p: p["_signal_score"], reverse=True)[:10]
    by_recent = sorted(
        posts,
        key=lambda p: (p.get("postedAt") or {}).get("timestamp", 0),
        reverse=True,
    )[:3]

    seen, merged = set(), []
    for p in by_score + by_recent:
        pid = p.get("id") or p.get("linkedinUrl")
        if pid not in seen:
            seen.add(pid)
            merged.append(p)

    return merged


async def analyze_posts(posts: List[Dict], provider=None) -> Dict[str, Any]:
    """Run the filtered posts through the LLM and return the 6 signal fields."""
    if not posts:
        return {}

    if provider is None:
        from backend.infra.llm.factory import get_llm_provider
        provider = get_llm_provider()

    slim_posts = [
        {
            "text":     p.get("content") or "",
            "date":     (p.get("postedAt") or {}).get("date", "")[:10],
            "type":     p.get("type", "post"),
            "likes":    (p.get("engagement") or {}).get("likes", 0),
            "comments": (p.get("engagement") or {}).get("comments", 0),
            "shares":   (p.get("engagement") or {}).get("shares", 0),
        }
        for p in posts
    ]

    wealth_keywords  = [kw for terms in WEALTH_SIGNAL_TERMS.values()  for kw in terms]
    giving_keywords  = [kw for terms in GIVING_SIGNAL_TERMS.values()   for kw in terms]
    personality_desc = "\n".join(f'    "{k}": {v}' for k, v in PERSONALITY_TYPES.items())
    engagement_desc  = (
        f'High = avg likes >= {ENGAGEMENT_THRESHOLDS["High"]}, '
        f'Medium = {ENGAGEMENT_THRESHOLDS["Medium"]}–{ENGAGEMENT_THRESHOLDS["High"]-1}, '
        f'Low = below {ENGAGEMENT_THRESHOLDS["Medium"]}'
    )

    prompt = f"""You are analyzing LinkedIn posts for fundraising intelligence.
This person is a high-net-worth prospect. Be precise — only flag what is clearly present.

Posts (highest-signal + most recent):
{json.dumps(slim_posts, indent=2)}

Extract these 6 fields as a JSON object:

1. "post_wealth_signal"
   Did this person mention or share content related to any of these events?
   Keywords to watch: {wealth_keywords}
   → One clear sentence if found. null if not present.

2. "post_giving_signal"
   Did this person personally give, pledge, volunteer, or express genuine charitable intent?
   Keywords to watch: {giving_keywords}
   IMPORTANT: Only flag real personal giving behaviour — past or present acts by the person themselves.
   Do NOT flag: conditional promises ("we'll donate if…"), company marketing copy, hypothetical giving,
   third-party fundraising announcements, or posts merely mentioning a charity without personal involvement.
   → One clear sentence describing the actual act if found. null if not present.

3. "post_topic_themes"
   What 2–4 subjects does this person post about most consistently?
   → JSON array of short lowercase tags, e.g. ["manufacturing", "AI", "climate"].

4. "post_engagement_tier"
   Based on average likes across the posts provided:
   {engagement_desc}
   → One of: "High", "Medium", "Low".

5. "post_personality_type"
   Which posting style best describes this person?
{personality_desc}
   → One of: "thought_leader", "curator", "self_promoter", "passive".

6. "post_last_active"
   Date of the most recent post as YYYY-MM-DD.

Return ONLY a valid JSON object. Omit any field you cannot confidently populate."""

    messages = [
        {"role": "system", "content": (
            "You extract structured signals from LinkedIn posts for fundraising teams. "
            "Respond with valid JSON only — no markdown, no explanation."
        )},
        {"role": "user", "content": prompt},
    ]

    result = await provider.complete(messages, model=Config.OPENAI_MODEL, temperature=0.1)
    return _parse(result)


def build_analyzed_links(posts: List[Dict]) -> str:
    """Build the post_analyzed_links field: one line per post with URL, engagement, and date."""
    lines = []
    for p in posts:
        url      = p.get("linkedinUrl") or p.get("shareLinkedinUrl") or ""
        eng      = p.get("engagement") or {}
        likes    = eng.get("likes", 0)
        comments = eng.get("comments", 0)
        date     = (p.get("postedAt") or {}).get("date", "")[:10]
        lines.append(f"{url}  ({likes} likes · {comments} comments · {date})")
    return "\n".join(lines)


async def extract_post_signals(raw_posts: List[Dict], provider=None) -> Dict[str, Any]:
    """Full pipeline: filter → LLM extract → build metadata."""
    if not raw_posts:
        return {}

    filtered = pre_filter_posts(raw_posts)
    signals  = await analyze_posts(filtered, provider=provider)
    signals["post_analyzed_links"] = build_analyzed_links(filtered)
    return signals


async def extract_personalization_hook(profile: Dict[str, Any], provider=None) -> Dict[str, Any]:
    """
    Produce ONE concrete, true INSIGHT about who this person is — grounded only in
    the scraped profile + recent posts. This is CONTEXT for the email writer to
    draw on (so it can open relevantly), NOT a line to paste verbatim.

    Goal-agnostic on purpose: it's generated at enrichment time before any campaign
    exists, so it states neutral facts (role, trajectory, recent focus) and lets the
    email agent decide what's relevant to the specific campaign.

    Returns {"personalization_hook": "<insight>"} or {} when there is nothing
    specific and true to say (better to say nothing than to fabricate).
    """
    if provider is None:
        from backend.infra.llm.factory import get_llm_provider
        provider = get_llm_provider()

    name     = (profile.get("full_name") or "").strip()
    headline = (profile.get("headline") or "").strip()
    title    = (profile.get("current_title") or profile.get("job_title") or "").strip()
    company  = (profile.get("current_company") or profile.get("company_name") or "").strip()

    raw = profile.get("raw_data") or {}
    experiences = raw.get("experiences") or raw.get("experience") or []
    exp_summary = "; ".join(
        f"{e.get('title','')} at {e.get('subtitle') or e.get('company') or ''}".strip(" at")
        for e in experiences[:4] if isinstance(e, dict)
    )

    recent_posts = []
    for p in (profile.get("posts") or [])[:5]:
        t = (p.get("content") or "").strip()
        if t:
            recent_posts.append(t[:280])

    # Nothing to ground a hook in → skip the call entirely.
    if not any([headline, title, company, exp_summary, recent_posts]):
        return {}

    prompt = f"""Write ONE factual insight about who this person is, for a fundraiser's reference.
This is CONTEXT to help compose a relevant email — it will NOT be pasted into the email verbatim.

RULES:
- Ground it ONLY in the facts below. NEVER invent companies, roles, achievements, posts, or interests.
- One sentence, ~12-25 words. Concrete and neutral — name their real role, career trajectory, or recent focus.
- State facts, not flattery. No clichés ("impressive", "thought leader", "inspiring").
- Stay campaign-agnostic: just describe who they are; don't guess what they'd donate to.
- If there is nothing specific and true to say, return null.

FACTS:
Name: {name or "unknown"}
Headline: {headline or "—"}
Current role: {title or "—"} at {company or "—"}
Career history: {exp_summary or "—"}
Recent posts: {json.dumps(recent_posts) if recent_posts else "none"}

Return ONLY JSON: {{"personalization_hook": "<insight>"}} or {{"personalization_hook": null}}"""

    messages = [
        {"role": "system", "content": (
            "You write a single factual, specific insight about a person for a fundraising team's "
            "reference. Never fabricate. Respond with valid JSON only."
        )},
        {"role": "user", "content": prompt},
    ]

    try:
        result = await provider.complete(messages, model=Config.OPENAI_MODEL, temperature=0.3)
        parsed = _parse(result)
        hook = (parsed.get("personalization_hook") or "").strip()
        return {"personalization_hook": hook} if hook and hook.lower() != "null" else {}
    except Exception as e:
        logger.warning(f"personalization_hook extraction failed (non-fatal): {e}")
        return {}


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _parse(content: str) -> Dict:
    try:
        if "```json" in content:
            content = content[content.find("```json") + 7 : content.rfind("```")]
        elif "```" in content:
            content = content[content.find("```") + 3 : content.rfind("```")]
        result = json.loads(content.strip())
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        logger.warning("linkedin/analyzer: failed to parse LLM JSON response")
        return {}
