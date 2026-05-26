"""
Pure-function scoring primitives for campaign contact segmentation.

All functions accept a raw Airtable 'fields' dict and return a float in [0, 1].
No I/O, no LLM, no side-effects — safe to call from parallel batch nodes.

Composite formula uses goal-adaptive weights derived at segmentation start.
Default fallback weights (used when LLM call fails):
  warm_path   0.25  — bridge contact exists in network graph
  post_signal 0.20  — philanthropic intent / giving history from posts
  rag         0.20  — semantic alignment with campaign goal (pgvector)
  capacity    0.15  — wealth / networth field text
  trajectory  0.10  — wealth trajectory archetype from enrichment
  topics      0.05  — topic interest alignment with campaign goal keywords
  engagement  0.05  — social posting engagement tier

Composite scoring (see compute_composite):
  - re-normalised over present signals (missing data doesn't deflate a contact)
  - dampened by signal coverage (a single thin signal can't masquerade as strong)

Tier assignment is distribution-relative, decided across the whole campaign in
finalize (see compute_tier_cutoffs / tier_from_distribution), not per-contact:
  - quantile cutoffs (top ~15% tier_1, next ~35% tier_2, rest tier_3)
  - guarded by absolute score floors
  - lifted by single-signal promotion floors (tier_floor_from_signals)

assign_tier (fixed absolute bands) is retained only as a legacy fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Field-name candidates ────────────────────────────────────────────────────
# Warm path writer may have used slightly different names across deploys.

_WARM_SCORE_FIELDS = [
    "warm_path_score", "Warm Path Score", "WarmPathScore",
    "warm_path_top_score", "wp_score",
]
_WARM_BRIDGE_FIELDS = [
    "warm_path_top_bridge", "Warm Path Top Bridge",
    "warm_path_bridge", "top_bridge", "Bridge Contact",
]
_WARM_EVIDENCE_FIELDS = [
    "warm_path_evidence", "Warm Path Evidence",
    "warm_path_top_evidence", "Bridge Evidence",
]

# ── Capacity tier keywords → score ───────────────────────────────────────────

_CAPACITY_TIERS: list[tuple[list[str], float]] = [
    (["$100m", "$50m", "ultra-high", "billionaire",
      "centi-millionaire", "family office", "ultra high net"], 1.0),
    (["$20m", "$10m", "very high", "hnwi", "high net worth"], 0.8),
    (["$5m", "$1m", "high", "affluent", "accredited"], 0.6),
    (["$500k", "$250k", "$100k", "medium", "comfortable"], 0.4),
    (["wealth", "capacity", "net worth", "networth"], 0.2),
]

# ── Trajectory archetype → score ─────────────────────────────────────────────
# Archetypes set by the enrichment LLM; see intelligence/linkedin/analyzer.py.
# tier1 / tier2 values mean this contact is a warm-path target — those are
# already captured by warm_path_score so we skip them here.

_TRAJECTORY_SCORES: dict[str, float] = {
    "exited_founder":        1.0,
    "serial_founder":        1.0,
    "serial_early_employee": 0.8,
    "rsu_beneficiary":       0.8,
    "senior_operator":       0.6,
    "early_employee":        0.4,
    "unclear":               0.1,
}

_ENGAGEMENT_MAP: dict[str, float] = {"high": 1.0, "medium": 0.6, "low": 0.3}

# ── Goal-adaptive weights ─────────────────────────────────────────────────────

_DEFAULT_WEIGHTS: dict[str, float] = {
    'warm_path':   0.25,
    'post_signal': 0.20,
    'rag':         0.20,
    'capacity':    0.15,
    'trajectory':  0.10,
    'topics':      0.05,
    'engagement':  0.05,
}
_WEIGHT_KEYS = list(_DEFAULT_WEIGHTS.keys())


async def compute_goal_weights(goal: str) -> dict[str, float]:
    """
    Single LLM call — derive composite weights from the campaign goal.
    Runs concurrently with Airtable fetch so it adds zero latency.
    Falls back to _DEFAULT_WEIGHTS on any error.
    """
    from openai import AsyncOpenAI
    from backend.config import Config

    client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
    prompt = (
        f'Campaign goal: "{goal}"\n\n'
        "Assign composite scoring weights to rank donor prospects for this specific goal. "
        "Weights MUST sum exactly to 1.0.\n\n"
        "Components:\n"
        "  warm_path   — a warm introduction path exists (0.10–0.35)\n"
        "  post_signal — philanthropic intent in social posts (0.10–0.30)\n"
        "  rag         — semantic match with campaign goal (0.10–0.30)\n"
        "  capacity    — donor wealth/capacity signals (0.05–0.25)\n"
        "  trajectory  — wealth-building trajectory archetype (0.05–0.15)\n"
        "  topics      — topic-interest alignment with goal (0.03–0.15)\n"
        "  engagement  — social media engagement level (0.03–0.10)\n\n"
        "Guidance:\n"
        "- Major gift / large ask (millions) → raise warm_path and capacity\n"
        "- Cause-specific / issue-based goal → raise rag and topics\n"
        "- Broad / community / annual fund → raise post_signal and engagement\n"
        "- Every component must be > 0; they must sum to exactly 1.0\n\n"
        'Return ONLY valid JSON: {"warm_path": 0.xx, "post_signal": 0.xx, '
        '"rag": 0.xx, "capacity": 0.xx, "trajectory": 0.xx, '
        '"topics": 0.xx, "engagement": 0.xx}'
    )
    try:
        resp = await client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            response_format={'type': 'json_object'},
            temperature=0,
            max_tokens=150,
        )
        data    = json.loads(resp.choices[0].message.content or '{}')
        weights = {k: max(float(data.get(k, _DEFAULT_WEIGHTS[k])), 0.01) for k in _WEIGHT_KEYS}
        total   = sum(weights.values())
        normed  = {k: round(v / total, 4) for k, v in weights.items()}
        logger.info("Goal-adaptive weights for %r: %s", goal[:60], normed)
        return normed
    except Exception as exc:
        logger.warning("Goal weight LLM call failed (%s) — using defaults", exc)
        return dict(_DEFAULT_WEIGHTS)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _first(fields: dict, candidates: list[str]) -> Optional[str]:
    for name in candidates:
        val = fields.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


# ── Individual scorers ───────────────────────────────────────────────────────

def score_warm_path(fields: dict) -> tuple[float, Optional[dict]]:
    """
    Returns (normalised_score, warm_path_data | None).
    warm_path_data = {"connector", "score", "evidence"} — stored in DB
    for the review queue context panel.
    """
    raw = _first(fields, _WARM_SCORE_FIELDS)
    if raw is None:
        return 0.0, None
    try:
        score = float(raw)
    except (ValueError, TypeError):
        return 0.0, None
    if score <= 0:
        return 0.0, None

    return min(score / 100.0, 1.0), {
        "connector": _first(fields, _WARM_BRIDGE_FIELDS),
        "score": score,
        "evidence": _first(fields, _WARM_EVIDENCE_FIELDS),
    }


def score_capacity(fields: dict) -> float:
    raw = str(fields.get("Wealthy Capacity/Networth", "") or "").lower().strip()
    if not raw or raw in ("none", "unclear", "unknown", "n/a", "-"):
        return 0.0
    for keywords, level in _CAPACITY_TIERS:
        if any(k in raw for k in keywords):
            return level
    return 0.1  # populated but unrecognised → weak positive signal


def score_trajectory(fields: dict) -> float:
    """
    trajectory_tag is set by the enrichment pipeline to an archetype string
    (EXITED_FOUNDER, SERIAL_FOUNDER, etc.) or tier1/tier2 for warm-path targets.
    tier1/tier2 are already captured by warm_path_score — return 0 to avoid
    double-counting.
    """
    raw = str(fields.get("trajectory_tag", "") or "").lower().strip()
    if not raw or raw in ("tier1", "tier2", "tier 1", "tier 2"):
        return 0.0
    return _TRAJECTORY_SCORES.get(raw, 0.0)


def score_post_signal(fields: dict) -> float:
    """
    Post giving signal (primary) with wealth signal fallback.
    Dollar amounts or long descriptions (>80 chars) = strong signal.
    """
    giving = str(fields.get("post_giving_signal", "") or "").strip()
    if giving:
        if re.search(r'\$[\d,]+', giving) or len(giving) > 80:
            return 0.9
        if len(giving) > 30:
            return 0.6
        return 0.35

    wealth = str(fields.get("post_wealth_signal", "") or "").strip()
    if wealth and len(wealth) > 20:
        return 0.25
    return 0.0


def score_engagement(fields: dict) -> float:
    tier = str(fields.get("post_engagement_tier", "") or "").lower().strip()
    return _ENGAGEMENT_MAP.get(tier, 0.0)


# ── Topic scoring ─────────────────────────────────────────────────────────────

_TOPIC_STOPWORDS: frozenset[str] = frozenset({
    "for", "the", "to", "a", "an", "and", "or", "of", "in", "at", "by",
    "from", "with", "raise", "fund", "our", "we", "my", "your", "this",
    "that", "will", "have", "build", "create", "help", "support", "its",
    "their", "who", "which", "are", "was", "were", "has", "had", "not",
    "but", "all", "one", "into", "about", "up", "out", "on", "be", "is",
})


def extract_goal_keywords(goal: str) -> frozenset[str]:
    """
    Extract meaningful keywords from a campaign goal string.
    Returns a frozenset so it is safely hashable and sharable across batch nodes.
    """
    words = re.findall(r'\b[a-z]+\b', goal.lower())
    return frozenset(w for w in words if w not in _TOPIC_STOPWORDS and len(w) > 2)


def score_topics(fields: dict, goal_keywords: frozenset[str]) -> float:
    """
    Intersection of contact's enriched topic interests with campaign goal keywords.
    Adds signal beyond RAG for contacts with sparse profiles or un-embedded records.
    """
    if not goal_keywords:
        return 0.0

    raw = str(fields.get("post_topic_themes", "") or "").strip()
    if not raw:
        return 0.0

    topics: list[str] = []
    if raw.startswith("["):
        try:
            topics = json.loads(raw.replace("'", '"'))
        except Exception:
            topics = [raw]
    else:
        topics = [t.strip() for t in raw.split(",")]

    # Flatten topic phrases to individual words for fuzzy matching
    topic_words: set[str] = set()
    for t in topics:
        topic_words.update(t.lower().replace("-", " ").split())

    matches = topic_words & goal_keywords
    if not matches:
        return 0.0

    # Scale by fraction of goal keywords hit; cap at 1.0
    return min(len(matches) / max(len(goal_keywords), 1) * 2.5, 1.0)


# ── Composite ────────────────────────────────────────────────────────────────

def compute_composite(
    warm_path: float,
    post_signal: float,
    rag: float,
    capacity: float,
    trajectory: float,
    engagement: float,
    topics: float = 0.0,
    weights: Optional[dict] = None,
) -> float:
    """
    Confidence-adjusted composite score in [0, 1].

    Two adjustments over a plain weighted sum:

    1. RE-NORMALISE OVER PRESENT SIGNALS — a component scores 0 when we simply
       have no data for it (no warm path, not embedded, no networth field…).
       Dividing by the weight of *present* signals only means a contact is judged
       on what we actually know, not penalised for data we never collected.
       A fully-enriched contact (all signals present) is unaffected — its
       present-weight is 1.0, so the result equals the plain weighted sum.

    2. COVERAGE DAMPENER — re-normalising alone would let a single thin signal
       (e.g. only "low engagement") rank like a fully-evidenced prospect.
       We scale by a gentle confidence factor (0.5–1.0) tied to how much signal
       weight is present, so thin-data contacts are discounted, not inflated.
    """
    w = weights or _DEFAULT_WEIGHTS
    comps = {
        'warm_path':   warm_path,
        'post_signal': post_signal,
        'rag':         rag,
        'capacity':    capacity,
        'trajectory':  trajectory,
        'topics':      topics,
        'engagement':  engagement,
    }

    weighted       = sum(comps[k] * w.get(k, 0.0) for k in comps)
    present_weight = sum(w.get(k, 0.0) for k in comps if comps[k] > 0)
    if present_weight <= 0:
        return 0.0

    renormalized = weighted / present_weight          # quality given what we know
    confidence   = 0.5 + 0.5 * min(present_weight, 1.0)  # coverage dampener [0.5, 1.0]
    return round(renormalized * confidence, 4)


# ── Single-signal promotion floors ────────────────────────────────────────────
# A linear score buries a contact whose value rests on ONE dominant signal —
# e.g. a $100M-capacity prospect with no warm path or embedding. In fundraising
# any one strong signal warrants attention, so we floor the tier accordingly,
# regardless of the composite.

def tier_floor_from_signals(breakdown: dict) -> Optional[str]:
    """Return the minimum tier a contact qualifies for on a single strong signal."""
    warm   = breakdown.get('warm_path', 0.0)
    cap    = breakdown.get('capacity', 0.0)
    giving = breakdown.get('post_signal', 0.0)
    traj   = breakdown.get('trajectory', 0.0)

    # Strong single signal → tier_1 floor
    if warm >= 0.70 or cap >= 1.0 or giving >= 0.85:
        return "tier_1"
    # Moderate single signal → tier_2 floor
    if warm >= 0.40 or cap >= 0.60 or giving >= 0.60 or traj >= 0.80:
        return "tier_2"
    return None


# ── Distribution-relative tier cutoffs ─────────────────────────────────────────
# Absolute thresholds collapse when warm_path/RAG are sparse (common): the max
# achievable score drops and almost everyone lands in tier_3. We derive cutoffs
# from THIS campaign's actual score distribution (quantiles), guarded by absolute
# floors so we never label the "top X% of weak scores" as tier_1.

_T1_QUANTILE  = 0.15   # top ~15% → tier_1
_T2_QUANTILE  = 0.50   # next ~35% → tier_2 (cumulative 50%)
_T1_MIN_SCORE = 0.30   # never tier_1 below this, however high the percentile
_T2_MIN_SCORE = 0.12   # never tier_2 below this

_TIER_RANK = {"tier_1": 3, "tier_2": 2, "tier_3": 1}


def compute_tier_cutoffs(scores: list[float]) -> tuple[float, float]:
    """Return (tier_1_cutoff, tier_2_cutoff) from the score distribution."""
    if not scores:
        return _T1_MIN_SCORE, _T2_MIN_SCORE
    ordered = sorted(scores, reverse=True)
    n = len(ordered)
    t1_idx = min(n - 1, max(0, int(n * _T1_QUANTILE) - 1))
    t2_idx = min(n - 1, max(0, int(n * _T2_QUANTILE) - 1))
    return max(ordered[t1_idx], _T1_MIN_SCORE), max(ordered[t2_idx], _T2_MIN_SCORE)


def tier_from_distribution(score: float, breakdown: dict, t1_cut: float, t2_cut: float) -> str:
    """Assign a tier from the distribution cutoffs, then lift it by any signal floor."""
    by_score = "tier_1" if score >= t1_cut else "tier_2" if score >= t2_cut else "tier_3"
    floor = tier_floor_from_signals(breakdown)
    if floor and _TIER_RANK[floor] > _TIER_RANK[by_score]:
        return floor
    return by_score


def extract_display_info(fields: dict, field_map: dict | None = None) -> dict:
    """
    Pull identity + key signal text from Airtable fields.
    Stored in contact_snapshot so the review queue never needs to re-fetch Airtable.

    field_map is {canonical_key: airtable_field_name} built from the saved mapping.
    When present, we use the exact field name — no guessing.
    Falls back to a candidate list when a key is absent from the map.
    """
    fm = field_map or {}

    def _mapped(canonical_keys: list[str], fallbacks: list[str]) -> Optional[str]:
        for ck in canonical_keys:
            airtable_name = fm.get(ck)
            if airtable_name:
                val = _first(fields, [airtable_name])
                if val:
                    return val
        return _first(fields, fallbacks)

    def _clean(val) -> Optional[str]:
        if not val:
            return None
        s = str(val).strip()
        return s if s and s.lower() not in ("none", "null", "n/a", "-", "unknown") else None

    # Name: try full_name mapping first, then construct from first+last
    full = _mapped(["full_name", "name"], ["Full Name", "Name", "full_name", "name"])
    if not full:
        first = _mapped(["first_name"], ["First Name", "first_name", "FirstName", "first"])
        last  = _mapped(["last_name"],  ["Last Name",  "last_name",  "LastName",  "last"])
        full  = f"{first or ''} {last or ''}".strip() or "Unknown"

    # Serialize all Airtable fields as strings for custom variable resolution.
    # Skips complex objects (lists, dicts) and blank/null values.
    def _scalar(v) -> Optional[str]:
        if v is None or isinstance(v, (list, dict)):
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ('', 'none', 'null', 'n/a', '-', 'unknown') else None

    raw_fields = {k: _scalar(v) for k, v in fields.items() if _scalar(v) is not None}

    return {
        "name":    full,
        "title":   _mapped(["job_title", "title", "current_title", "headline"],
                           ["Job Title", "Title", "Current Title", "job_title",
                            "Headline", "headline", "Position", "Role"]),
        "company": _mapped(["current_company", "company", "company_name"],
                           ["Company Name", "Company", "Current Company", "company_name",
                            "Organization", "Organisation", "Employer", "Firm"]),
        "email":   _mapped(["email", "email_address"],
                           ["Email", "email", "Email Address"]),
        "signals": {
            "giving":      _clean(fields.get("post_giving_signal")),
            "wealth":      _clean(fields.get("post_wealth_signal")),
            "capacity":    _clean(fields.get("Wealthy Capacity/Networth")),
            "trajectory":  _clean(fields.get("trajectory_tag")),
            "engagement":  _clean(fields.get("post_engagement_tier")),
            "topics":      _clean(fields.get("post_topic_themes")),
            "personality": _clean(fields.get("post_personality_type")),
        },
        "raw_fields": raw_fields,
    }


def assign_tier(composite_score: float) -> str:
    """
    Three tiers based on composite score bands.
    tier_1 — highest signal (≥ 0.45)
    tier_2 — mid signal    (≥ 0.20)
    tier_3 — low signal    (< 0.20)
    """
    if composite_score >= 0.45:
        return "tier_1"
    if composite_score >= 0.20:
        return "tier_2"
    return "tier_3"
