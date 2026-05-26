"""
Twitter/X Posts Intelligence Analyzer

Takes raw Apify tweet output and extracts structured fundraising signals
via a single LLM call — same pattern as analyzer.py for LinkedIn.

Pipeline:
  1. pre_filter_tweets()  — score + rank tweets, keep highest-signal subset (no LLM)
  2. analyze_tweets()     — LLM extracts signal fields
  3. build_metadata()     — assemble tweet_analyzed_links (no LLM)

Output fields:
  tweet_wealth_signal    — liquidity / investment events mentioned in tweets
  tweet_giving_signal    — philanthropic activity or intent
  tweet_topic_themes     — recurring subjects the person tweets about
  tweet_engagement_tier  — audience reach inferred from avg likes/views
  tweet_personality_type — posting style / voice
  tweet_last_active      — date of most recent tweet
  tweet_analyzed_links   — URLs + engagement of tweets sent to the LLM
"""

import json
import logging
from typing import Any, Dict, List

from backend.config import Config
from backend.infra.llm import LLMProvider
from backend.intelligence.shared.keywords import (
    WEALTH_SIGNAL_TERMS,
    GIVING_SIGNAL_TERMS,
    PERSONALITY_TYPES,
)

logger = logging.getLogger(__name__)

TWEET_SIGNAL_FIELDS: Dict[str, str] = {
    "tweet_wealth_signal":    "multilineText",
    "tweet_giving_signal":    "multilineText",
    "tweet_topic_themes":     "multipleSelects",
    "tweet_engagement_tier":  "singleSelect",
    "tweet_personality_type": "singleSelect",
    "tweet_last_active":      "singleLineText",
    "tweet_analyzed_links":   "multilineText",
}

# Calibrated for Twitter — views make engagement thresholds much higher than LinkedIn
ENGAGEMENT_THRESHOLDS = {
    "High":   500,    # avg likes >= 500 → significant reach
    "Medium":  50,    # avg likes 50–499 → moderate reach
    "Low":      0,    # avg likes < 50  → limited reach
}


# ---------------------------------------------------------------------------
# Step 1 — Pre-filter: score and rank tweets before sending to LLM
# ---------------------------------------------------------------------------

def pre_filter_tweets(tweets: List[Dict]) -> List[Dict]:
    """
    Score each tweet by fundraising signal value and return the top subset.

    Scoring weights:
      - Replies weighted 3x likes (active engagement)
      - Retweets weighted 2x likes (amplification signal)
      - Original tweets scored 10x higher than retweets (original voice = stronger signal)
      - Views counted at 0.01x (directional reach signal, not engagement depth)

    Returns up to 13 tweets: top 10 by score + 3 most recent (deduplicated).
    """
    for tweet in tweets:
        likes    = tweet.get("likes", 0) or 0
        retweets = tweet.get("retweets", 0) or 0
        replies  = tweet.get("replies", 0) or 0
        views    = tweet.get("views", 0) or 0
        is_original = 0 if tweet.get("is_retweet") else 10

        tweet["_signal_score"] = (
            likes    * 1 +
            replies  * 3 +
            retweets * 2 +
            views    * 0.01 +
            is_original
        )

    by_score  = sorted(tweets, key=lambda t: t["_signal_score"], reverse=True)[:10]
    by_recent = sorted(
        tweets,
        key=lambda t: t.get("created_at") or "",
        reverse=True
    )[:3]

    seen = set()
    merged = []
    for t in by_score + by_recent:
        tid = t.get("tweet_id") or t.get("url")
        if tid not in seen:
            seen.add(tid)
            merged.append(t)

    return merged


# ---------------------------------------------------------------------------
# Step 2 — LLM extraction
# ---------------------------------------------------------------------------

async def analyze_tweets(tweets: List[Dict], provider: LLMProvider | None = None) -> Dict[str, Any]:
    """
    Run the filtered tweets through the LLM and return the signal fields.
    """
    if not tweets:
        return {}

    if provider is None:
        from backend.infra.llm.factory import get_llm_provider
        provider = get_llm_provider()

    slim_tweets = [
        {
            "text":      t.get("text") or "",
            "date":      (t.get("created_at") or "")[:10],
            "is_retweet": t.get("is_retweet", False),
            "likes":     t.get("likes", 0),
            "retweets":  t.get("retweets", 0),
            "replies":   t.get("replies", 0),
            "views":     t.get("views", 0),
        }
        for t in tweets
    ]

    wealth_keywords  = [kw for terms in WEALTH_SIGNAL_TERMS.values()  for kw in terms]
    giving_keywords  = [kw for terms in GIVING_SIGNAL_TERMS.values()   for kw in terms]
    personality_desc = "\n".join(f'    "{k}": {v}' for k, v in PERSONALITY_TYPES.items())
    engagement_desc  = (
        f'High = avg likes >= {ENGAGEMENT_THRESHOLDS["High"]}, '
        f'Medium = {ENGAGEMENT_THRESHOLDS["Medium"]}–{ENGAGEMENT_THRESHOLDS["High"]-1}, '
        f'Low = below {ENGAGEMENT_THRESHOLDS["Medium"]}'
    )

    prompt = f"""You are analyzing Twitter/X posts for fundraising intelligence.
This person is a high-net-worth prospect. Be precise — only flag what is clearly present.

Tweets (highest-signal + most recent):
{json.dumps(slim_tweets, indent=2)}

Extract these 6 fields as a JSON object:

1. "tweet_wealth_signal"
   Did this person mention or share content about any of these events?
   Keywords to watch: {wealth_keywords}
   → One clear sentence if found (e.g. "Announced Series B close, retweeted funding news Apr 2024").
     null if not present.

2. "tweet_giving_signal"
   Did this person mention philanthropy, donations, causes, or charitable intent?
   Keywords to watch: {giving_keywords}
   → One clear sentence if found. null if not present.

3. "tweet_topic_themes"
   What 2–4 subjects does this person tweet about most consistently?
   → JSON array of short lowercase tags, e.g. ["venture capital", "AI", "climate"].

4. "tweet_engagement_tier"
   Based on average likes across the tweets provided:
   {engagement_desc}
   → One of: "High", "Medium", "Low".

5. "tweet_personality_type"
   Which posting style best describes this person?
{personality_desc}
   → One of: "thought_leader", "curator", "self_promoter", "passive".

6. "tweet_last_active"
   Date of the most recent tweet as YYYY-MM-DD.

Return ONLY a valid JSON object. Omit any field you cannot confidently populate."""

    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured signals from Twitter/X posts for fundraising teams. "
                "Respond with valid JSON only — no markdown, no explanation."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    result = await provider.complete(messages, model=Config.OPENAI_MODEL, temperature=0.1)
    return _parse(result)


# ---------------------------------------------------------------------------
# Step 3 — Metadata (no LLM)
# ---------------------------------------------------------------------------

def build_analyzed_links(tweets: List[Dict]) -> str:
    """
    Build the tweet_analyzed_links field: one line per tweet with URL + engagement.

    Example output:
      https://twitter.com/aaronbird/status/123  (420 likes · 38 RT · 2024-04-11)
    """
    lines = []
    for t in tweets:
        url      = t.get("url") or ""
        likes    = t.get("likes", 0)
        retweets = t.get("retweets", 0)
        date     = (t.get("created_at") or "")[:10]
        lines.append(f"{url}  ({likes} likes · {retweets} RT · {date})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def extract_tweet_signals(raw_tweets: List[Dict], provider: LLMProvider | None = None) -> Dict[str, Any]:
    """
    Full pipeline: filter → LLM extract → build metadata.
    Returns a dict ready to merge into the Airtable field update.
    """
    if not raw_tweets:
        return {}

    filtered = pre_filter_tweets(raw_tweets)
    signals  = await analyze_tweets(filtered, provider=provider)
    signals["tweet_analyzed_links"] = build_analyzed_links(filtered)
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
        logger.warning("twitter_analyzer: failed to parse LLM JSON response")
        return {}
