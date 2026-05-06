"""
Shared signal keyword dictionaries used by both LinkedIn and Twitter analyzers.

These constants define what the LLM looks for when extracting fundraising signals
from posts and tweets. Update these to tune what gets flagged.
"""

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
# Note: LinkedIn and Twitter variants have slightly different descriptions — these are
# the canonical definitions. Each analyzer's prompt may adapt the wording for context.
PERSONALITY_TYPES = {
    "thought_leader": "Writes original long-form opinions, arguments, or industry takes. "
                      "High comments/replies relative to likes.",
    "curator":        "Primarily reposts or shares others' content, sometimes with brief commentary. "
                      "Reposts outnumber original posts.",
    "self_promoter":  "Posts focus on personal wins, company news, awards, press coverage. "
                      "Content is mostly about themselves or their company.",
    "passive":        "Posts infrequently or has very low engagement. "
                      "Not an active social media voice.",
}
