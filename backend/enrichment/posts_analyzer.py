"""
Posts Intelligence Analyzer

Takes raw harvestapi/linkedin-profile-posts output and extracts 7 structured
fundraising signals via a single LLM call.

Pipeline:
  1. pre_filter_posts()  — score + rank posts, keep highest-signal subset (no LLM)
  2. analyze_posts()     — LLM extracts the 6 signal fields
  3. build_metadata()    — assemble post_analyzed_links (no LLM)

Output fields (written to Airtable):
  post_wealth_signal    — liquidity / investment events mentioned in posts
  post_giving_signal    — philanthropic activity or intent
  post_topic_themes     — recurring subjects the person posts about
  post_engagement_tier  — audience reach inferred from avg likes/comments
  post_personality_type — posting style / voice
  post_last_active      — date of most recent post
  post_analyzed_links   — URLs + engagement of the posts sent to the LLM
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.config import Config

logger = logging.getLogger(__name__)

# Airtable field name → type for the 7 posts signal fields.
# Used by batch_executor to extend CSV headers and the Airtable flush type map.
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
# Signal keyword dictionaries — update these to tune what gets flagged.
# Each key becomes a possible value in post_wealth_signal / post_giving_signal.
# ---------------------------------------------------------------------------

# Terms that indicate a liquidity event, financial win, or investment activity.
# Used by the LLM prompt as explicit guidance — not for regex matching.
WEALTH_SIGNAL_TERMS = {
    "acquisition":   ["acquired", "acquisition", "acqui-hire", "bought by", "sold to", "merger"],
    "ipo":           ["IPO", "went public", "listed on", "NYSE", "NASDAQ", "stock market"],
    "fundraise":     ["raised", "Series A", "Series B", "Series C", "seed round", "funding round",
                      "closed our round", "we raised", "announced funding"],
    "exit":          ["exit", "exited", "sold the company", "liquidity event"],
    "investment":    ["invested in", "led the round", "participated in", "portfolio company",
                      "angel investment", "we invested"],
    "fund_close":    ["closed our fund", "fund close", "first close", "final close", "new fund"],
}

# Terms that indicate philanthropic intent, charitable giving, or cause alignment.
# Fundraisers use this to assess mission fit before outreach.
GIVING_SIGNAL_TERMS = {
    "donation":      ["donated", "donation", "gave", "gift", "contributed", "contributing"],
    "cause_mention": ["nonprofit", "non-profit", "foundation", "charity", "charitable",
                      "501(c)", "social impact", "mission-driven"],
    "pledge":        ["pledged", "pledge", "matching", "match my donation", "giving pledge",
                      "committed to", "committing"],
    "volunteering":  ["volunteered", "volunteering", "pro bono", "board member", "advisory board"],
    "impact_invest": ["impact investing", "ESG", "sustainable", "double bottom line",
                      "social enterprise", "B Corp"],
}

# Personality archetypes — one is assigned per contact based on posting style.
# Used in outreach strategy: thought leaders get engaged with their ideas;
# curators get referenced for what they share; self-promoters respond to recognition.
PERSONALITY_TYPES = {
    "thought_leader": "Writes original long-form opinions, arguments, or industry takes. "
                      "High comments relative to likes.",
    "curator":        "Primarily reposts or shares others' content, sometimes with brief commentary. "
                      "Reposts outnumber original posts.",
    "self_promoter":  "Posts focus on personal wins, company news, awards, press coverage. "
                      "Content is mostly about themselves or their company.",
    "passive":        "Posts infrequently (fewer than 5 in the scraped set) or has very low "
                      "engagement (avg likes < 10). Not an active LinkedIn voice.",
}

# Engagement thresholds for post_engagement_tier.
# Calibrated for a professional LinkedIn audience (not a consumer influencer audience).
ENGAGEMENT_THRESHOLDS = {
    "High":   100,   # avg likes >= 100 → significant reach, posts travel beyond network
    "Medium":  20,   # avg likes 20–99 → moderate reach, engaged first-degree network
    "Low":      0,   # avg likes < 20  → limited reach or infrequent poster
}


# ---------------------------------------------------------------------------
# Step 1 — Pre-filter: score and rank posts before sending to LLM
# ---------------------------------------------------------------------------

def pre_filter_posts(posts: List[Dict]) -> List[Dict]:
    """
    Score each post by fundraising signal value and return the top subset.

    Scoring weights:
      - Comments weighted 3x likes (a comment = active engagement, not a passive like)
      - Shares weighted 2x likes (sharing = amplification, implies strong agreement)
      - Original posts scored 10x higher than reposts (original content = stronger voice signal)

    Returns up to 13 posts: top 10 by score + 3 most recent (deduplicated).
    The 3 most recent are always included regardless of engagement to capture current activity.
    """
    for post in posts:
        engagement = post.get("engagement") or {}
        likes    = engagement.get("likes", 0)    or 0
        comments = engagement.get("comments", 0) or 0
        shares   = engagement.get("shares", 0)   or 0
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
        reverse=True
    )[:3]

    seen = set()
    merged = []
    for p in by_score + by_recent:
        pid = p.get("id") or p.get("linkedinUrl")
        if pid not in seen:
            seen.add(pid)
            merged.append(p)

    return merged


# ---------------------------------------------------------------------------
# Step 2 — LLM extraction
# ---------------------------------------------------------------------------

async def analyze_posts(posts: List[Dict], llm: Optional[ChatOpenAI] = None) -> Dict[str, Any]:
    """
    Run the filtered posts through the LLM and return the 6 signal fields.

    The prompt explicitly references WEALTH_SIGNAL_TERMS and GIVING_SIGNAL_TERMS
    so the model knows exactly what to look for rather than improvising.
    """
    if not posts:
        return {}

    if llm is None:
        llm = ChatOpenAI(
            model=Config.OPENAI_MODEL,
            temperature=0.1,
            api_key=Config.OPENAI_API_KEY,
        )

    # Slim down each post to only what the LLM needs — strip image/video blobs
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
   → One clear sentence if found (e.g. "Announced Nanotronics raised Series C, Apr 2024").
     null if not present.

2. "post_giving_signal"
   Did this person mention philanthropy, donations, causes, or charitable intent?
   Keywords to watch: {giving_keywords}
   → One clear sentence if found (e.g. "Shared commitment to climate nonprofits, tagged 2 orgs").
     null if not present.

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
        SystemMessage(content=(
            "You extract structured signals from LinkedIn posts for fundraising teams. "
            "Respond with valid JSON only — no markdown, no explanation."
        )),
        HumanMessage(content=prompt),
    ]

    response = await llm.ainvoke(messages)
    return _parse(response.content)


# ---------------------------------------------------------------------------
# Step 3 — Metadata (no LLM)
# ---------------------------------------------------------------------------

def build_analyzed_links(posts: List[Dict]) -> str:
    """
    Build the post_analyzed_links field: one line per post with URL, engagement, and date.
    No LLM needed — pure data assembly.

    Example output:
      https://linkedin.com/posts/nanotronics-...  (98 likes · 3 comments · 2024-04-11)
      https://linkedin.com/posts/cubefabs-...      (83 likes · 0 comments · 2023-12-07)
    """
    lines = []
    for p in posts:
        url      = p.get("linkedinUrl") or p.get("shareLinkedinUrl") or ""
        eng      = p.get("engagement") or {}
        likes    = eng.get("likes", 0)
        comments = eng.get("comments", 0)
        date     = (p.get("postedAt") or {}).get("date", "")[:10]
        lines.append(f"{url}  ({likes} likes · {comments} comments · {date})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def extract_post_signals(raw_posts: List[Dict], llm: Optional[ChatOpenAI] = None) -> Dict[str, Any]:
    """
    Full pipeline: filter → LLM extract → build metadata.
    Returns a dict ready to merge into the Airtable field update.
    """
    if not raw_posts:
        return {}

    filtered = pre_filter_posts(raw_posts)
    signals  = await analyze_posts(filtered, llm=llm)
    signals["post_analyzed_links"] = build_analyzed_links(filtered)
    return signals


# ---------------------------------------------------------------------------
# Helpers
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
        logger.warning("posts_analyzer: failed to parse LLM JSON response")
        return {}
