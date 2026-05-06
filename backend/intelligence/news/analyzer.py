"""
News Signal Analyzer

Takes raw Serper.dev /news results and extracts 4 press intelligence fields.
No LLM — pure keyword matching and data assembly.

Output fields (written to Airtable):
  press_count       — total articles found (number)
  top_outlets       — up to 5 outlet names, comma-separated (singleLineText)
  press_flags       — matched signal categories (multipleSelects)
  notable_headline  — most relevant article title + outlet + date (singleLineText)
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Airtable field name → type for the 4 news signal fields.
# Used by batch_executor to extend CSV headers and the Airtable flush type map.
NEWS_SIGNAL_FIELDS: Dict[str, str] = {
    "press_count":      "number",
    "top_outlets":      "singleLineText",
    "press_flags":      "multipleSelects",
    "notable_headline": "singleLineText",
}

# ---------------------------------------------------------------------------
# Flag keyword categories — scan article titles + snippets for these.
# Each key becomes a possible value in the press_flags multipleSelects field.
# Add new categories here — they automatically appear in Airtable options.
# ---------------------------------------------------------------------------

NEWS_FLAG_CATEGORIES: Dict[str, List[str]] = {
    "wealth_event": [
        "acquisition", "acquired", "acqui-hire", "ipo", "went public", "listed on",
        "raised", "funding", "series a", "series b", "series c", "seed round",
        "exit", "merger", "sold", "buyout", "valuation",
    ],
    "litigation": [
        "lawsuit", "sued", "settlement", "fraud", "charges", "indicted",
        "arrested", "investigation", "sec", "class action", "legal action",
    ],
    "leadership": [
        "appointed", "named ceo", "named president", "named chairman",
        "resigned", "steps down", "promoted", "joins as", "elected",
    ],
    "layoffs": [
        "layoffs", "lay off", "layoff", "cuts jobs", "job cuts",
        "downsizing", "restructuring", "workforce reduction",
    ],
    "philanthropy": [
        "donated", "donation", "foundation", "charity", "nonprofit",
        "philanthropist", "philanthropy", "giving", "grant", "endowment",
    ],
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_news_results(results: List[Dict], name: str) -> Dict[str, Any]:
    """
    Parse raw Serper /news results into the 4 press signal fields.

    Args:
        results: raw Serper news result objects
        name:    person's full name (used to find name-matched headlines)

    Returns:
        Dict keyed by field name. Always includes press_count (0 if no results).
    """
    if not results:
        return {"press_count": 0}

    press_count = len(results)

    # --- top_outlets: deduplicated, ordered by first appearance, max 5 ---
    seen: set = set()
    outlets: List[str] = []
    for r in results:
        source = (r.get("source") or "").strip()
        if source and source not in seen:
            seen.add(source)
            outlets.append(source)

    # --- press_flags: scan title + snippet for keyword categories ---
    flags: set = set()
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
        for category, keywords in NEWS_FLAG_CATEGORIES.items():
            if any(kw in text for kw in keywords):
                flags.add(category)

    # --- notable_headline: most relevant article mentioning the person by name ---
    notable = _find_notable(results, name)

    out: Dict[str, Any] = {"press_count": press_count}
    if outlets:
        out["top_outlets"] = ", ".join(outlets[:5])
    if flags:
        out["press_flags"] = sorted(flags)
    if notable:
        out["notable_headline"] = notable
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_notable(results: List[Dict], name: str) -> str:
    """
    Return the best headline: prefer an article whose title contains the person's
    first AND last name. Fall back to the first result if none match by name.
    Format: "Title — Source (date)"
    """
    name_parts = name.lower().split()
    first = name_parts[0] if name_parts else ""
    last  = name_parts[-1] if len(name_parts) > 1 else ""

    def _fmt(r: Dict) -> str:
        parts = [r.get("title", "").strip()]
        source = (r.get("source") or "").strip()
        date   = (r.get("date")   or "").strip()
        if source:
            parts.append(f"— {source}")
        if date:
            parts.append(f"({date})")
        return " ".join(p for p in parts if p)

    for r in results:
        title_lower = (r.get("title") or "").lower()
        if first and last and first in title_lower and last in title_lower:
            return _fmt(r)

    return _fmt(results[0]) if results else ""
