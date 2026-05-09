# Outreach System Design

## The Core Loop

```
Phase 1 — enrich once, establish baseline signals

Phase 3 — re-scrape on tier schedule, diff against baseline
              ↓
         delta detected → outreach trigger created

Phase 2 — trigger feeds the outreach queue
              ↓
         system drafts message with trigger as context
              ↓
         fundraiser reviews (HITL) → sends
              ↓
         response logged → contact stage updated
              ↓
         stage update can itself trigger next action
             (follow-up scheduled, intro requested, meeting booked)
```

The three phases depend on each other in order.
Phase 1 enriches once. Phase 3 keeps it fresh. Phase 2 acts on the freshness.

---

## Tiered Refresh Strategy

Not all contacts need the same scraping cadence. Segment by priority:

| Tier | Size | Who | Signals refreshed | Frequency |
|---|---|---|---|---|
| Hot | ~200 | wealth_confidence=High, active pipeline | Full: LinkedIn profile + posts + Twitter | Weekly |
| Warm | ~800 | Medium confidence, 2+ signals populated | Twitter + news only | Bi-weekly |
| Cold | rest | Low/no signals | News search only | Monthly |

The tier is not just a scraping budget decision — it maps to fundraiser attention.
A hot-tier trigger gets immediate review. A cold-tier trigger goes into a later queue.

**Cost profile per signal type:**
- News search (Serper) — ~$0.001 per query, run on everyone frequently
- Twitter re-scrape — moderate, only on contacts with known handle + active tier
- LinkedIn posts — moderate, active posters in hot tier only
- LinkedIn full profile — expensive, hot tier only

**Crunchbase is company-level, not person-level:**
Maintain a list of companies your top contacts work at. Query "any new funding events
for these companies?" daily — one cheap query per company rather than one expensive
person lookup per contact. Company raises a round → trigger for everyone at that company.

---

## The Diff Engine

On every re-scrape, compare new signals to the stored baseline. Any change is a trigger.

```python
def detect_triggers(stored: dict, fresh: dict) -> list[dict]:
    triggers = []

    if fresh['press_count'] > stored['press_count']:
        triggers.append({'type': 'news_hit', 'delta': fresh['press_count'] - stored['press_count']})

    if fresh.get('tweet_wealth_signal') and not stored.get('tweet_wealth_signal'):
        triggers.append({'type': 'wealth_signal_appeared', 'signal': fresh['tweet_wealth_signal']})

    if fresh.get('post_giving_signal') and not stored.get('post_giving_signal'):
        triggers.append({'type': 'giving_signal_appeared', 'signal': fresh['post_giving_signal']})

    if fresh.get('trajectory_tag') != stored.get('trajectory_tag'):
        triggers.append({'type': 'trajectory_changed',
                         'from': stored.get('trajectory_tag'),
                         'to': fresh.get('trajectory_tag')})

    # Crunchbase
    if fresh.get('notable_exits') and not stored.get('notable_exits'):
        triggers.append({'type': 'liquidity_event', 'detail': fresh['notable_exits']})

    return triggers
```

The diff history is the contact timeline. Every signal change is dated.
That timeline becomes the "why now" context the message drafter uses.

---

## Trigger Types

| Trigger | Source | Priority |
|---|---|---|
| Funding round / exit at contact's company | Crunchbase | High |
| New giving signal in posts or tweets | LinkedIn / Twitter | High |
| New wealth signal in posts or tweets | LinkedIn / Twitter | High |
| Trajectory tag changed to EXITED_FOUNDER | LinkedIn profile | High |
| News hit (press_count increase) | Serper news | Medium |
| Engagement spike on cause-related content | Twitter / LinkedIn | Medium |
| Contact became active after long silence | tweet_last_active / post_last_active | Low |

---

## Outreach Queue

The fundraiser opens their dashboard and sees triggers from the last refresh cycle:

> *"5 contacts triggered this week"*
> - Aaron Bird — new post mentioning climate tech (matches your cause)
> - Jane Smith — Series B closed at her company (Crunchbase)
> - Michael Chen — 3 news hits this week, up from 0

Not a live stream. A weekly digest is enough — fundraising doesn't need
millisecond reaction time. Reacting within days of a trigger beats cold
outreach with no trigger at all.

---

## Warm Path First

If `intro_strength_score` is above threshold, the recommended action is never
"send cold message" — it's "ask [team member] to introduce."

The system drafts the intro request for the team member, not a cold message
to the prospect. Cold outreach is the fallback when no warm path exists.

---

## Message Drafting

Draft generated from:
- Enriched contact profile (wealth signals, topic themes, personality type, causes)
- The triggering event (what happened, when)
- Warm path (who's connecting, strength of connection)
- Org mission and current campaign context
- Fundraiser's own voice (few-shot examples from past approved messages)

Opening must be specific to the person and the trigger — not generic.

**Example with trigger:**
> "Saw your post on Nanotronics' Series C — congratulations. The work you're doing
> in advanced manufacturing aligns closely with something we're building..."

HITL is non-negotiable. No outreach message leaves without human review and approval.

---

## Channel Selection

| Condition | Channel |
|---|---|
| Warm intro exists (intro_strength_score > threshold) | Intro request via email to mutual |
| tweet_engagement_tier = High | Twitter DM |
| post_engagement_tier = High | LinkedIn InMail |
| Email available | Email |
| Default | LinkedIn InMail |

No auto-send via API. Correct UX: "Copy message" or "Open LinkedIn compose."
Keeps human in the loop for the actual send.

---

## Sequence Management

Fundraising sequences are short and personal — not sales cadences:

1. Initial outreach
2. One follow-up at 10 days if no response
3. One final touch at 21 days
4. Cool-down: 90 days minimum before re-engaging

Contact stage tracked in Airtable:
`outreach_status`: not_started → contacted → responded → meeting_booked → declined → cooling

---

## Module Structure

```
backend/outreach/
├── ranker.py        — prospect scoring + queue generation from trigger pool
├── triggers.py      — diff engine + trigger type classification
├── drafter.py       — LLM message drafting with persona + trigger context
├── channels.py      — channel selection logic
├── sequences.py     — follow-up cadence state machine
└── workflows/
    └── outreach.py  — LangGraph workflow (mirrors enrichment.py shape)
```

The LangGraph workflow follows the same interrupt/resume pattern as
`agents/workflows/enrichment.py`. Nodes:
`prioritize → detect_trigger → select_channel → find_warm_path → draft → hitl_review → log_to_airtable → schedule_followup`

---

## Open Questions

- What signal threshold promotes a contact from cold → warm tier automatically?
- How is "org mission + current campaign" context injected into the drafter?
- Does the fundraiser configure their own voice examples, or does the system learn from approved messages over time?
- Where does sequence state live — Airtable fields or internal DB?
