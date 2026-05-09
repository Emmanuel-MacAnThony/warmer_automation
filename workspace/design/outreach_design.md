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

## Outreach Queue — What the Fundraiser Sees

The fundraiser opens their dashboard and sees triggers from the last refresh cycle.
Not a live stream — a weekly digest is enough.

```
OUTREACH QUEUE  ·  5 this week
────────────────────────────────────────────────────────────
Aaron Bird         EXITED_FOUNDER  ·  High wealth
                   🔔 New post about climate tech  ·  Warm path: Jeremiah
                   [Review →]

Jane Smith         RSU_BENEFICIARY  ·  High wealth
                   💰 Series B closed at her company (Crunchbase)
                   [Review →]

Michael Chen       SENIOR_OPERATOR  ·  Medium wealth
                   📰 3 news hits this week, up from 0
                   [Review →]
────────────────────────────────────────────────────────────
```

---

## The Outreach Card — Warm Path Exists

When clicking into a prospect, the fundraiser sees context first, then the draft.

```
┌──────────────────────────────────────────────────────────┐
│  Aaron Bird                                              │
│  CEO, Apexcel  ·  San Francisco                         │
│  Wealth: High  ·  Trajectory: EXITED_FOUNDER            │
├──────────────────────────────────────────────────────────┤
│  WHY NOW                                                 │
│  ● Posted about climate manufacturing 2 days ago        │
│  ● 2 news hits this week (up from 0)                    │
├──────────────────────────────────────────────────────────┤
│  WARM PATH                                               │
│  Jeremiah → Aaron Bird  (intro strength: Strong)        │
├──────────────────────────────────────────────────────────┤
│  INTRO REQUEST  →  Jeremiah                             │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Hi Jeremiah,                                       │  │
│  │                                                    │  │
│  │ Would you be able to intro me to Aaron Bird?       │  │
│  │ He posted about climate manufacturing this week    │  │
│  │ and I think there's a real alignment with our      │  │
│  │ work at [Org]. Happy to give you more context.     │  │
│  └────────────────────────────────────────────────────┘  │
│  [Copy]  [Open Gmail]                                    │
├──────────────────────────────────────────────────────────┤
│  FALLBACK — if no intro in 5 days, cold message below   │
│  [Show cold draft ↓]                                     │
└──────────────────────────────────────────────────────────┘
```

When a warm path exists, the intro request is the primary action.
Cold message is hidden behind "show fallback" — not presented as equal options.

---

## The Outreach Card — No Warm Path

When no intro path is found the system falls back to cold outreach.
The trigger compensates for the missing intro — a strong trigger makes cold
outreach feel relevant rather than random.

```
┌──────────────────────────────────────────────────────────┐
│  Jane Smith                                              │
│  CFO, Vertex Capital  ·  New York                       │
│  Wealth: High  ·  Trajectory: RSU_BENEFICIARY           │
├──────────────────────────────────────────────────────────┤
│  WHY NOW                                                 │
│  💰 Series B closed at Vertex Capital (Crunchbase)      │
│  📰 Featured in TechCrunch this week                    │
├──────────────────────────────────────────────────────────┤
│  WARM PATH                                               │
│  ⚠ No warm path found                                   │
├──────────────────────────────────────────────────────────┤
│  COLD MESSAGE  ·  LinkedIn InMail                       │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Hi Jane,                                           │  │
│  │                                                    │  │
│  │ Congratulations on the Series B — well deserved    │  │
│  │ given what Vertex has been building. I'm [Name]    │  │
│  │ at [Org], and the timing feels right to share      │  │
│  │ what we're working on. The alignment with your     │  │
│  │ work in [field] is hard to ignore.                 │  │
│  │                                                    │  │
│  │ Would a 20-minute call work this month?            │  │
│  └────────────────────────────────────────────────────┘  │
│  [Edit]  [Regenerate]                                    │
├──────────────────────────────────────────────────────────┤
│  [Copy message]  [Open LinkedIn]  [Snooze 7d]  [Skip]   │
└──────────────────────────────────────────────────────────┘
```

### When to go cold vs wait

Not every trigger justifies cold outreach. The system applies this logic:

| Trigger strength | Warm path | Action |
|---|---|---|
| High (funding event, giving signal, trajectory change) | Yes | Draft intro request |
| High | No | Draft cold message — trigger is strong enough |
| Medium (single news hit) | Yes | Draft intro request |
| Medium | No | Flag as "wait for stronger trigger or find intro" — do not queue |
| None (profile signals only) | Any | Do not queue — monitor only |

The rule: **cold outreach without a trigger is spam. Cold outreach with a strong
trigger is timely.** The trigger is doing the work the intro would otherwise do.

---

## Follow-Up — 10 Days Later

After the fundraiser marks a message as sent, a follow-up item appears in
the queue automatically.

```
┌──────────────────────────────────────────────────────────┐
│  FOLLOW-UP DUE  ·  Aaron Bird                           │
│  Contacted 10 days ago via LinkedIn InMail  ·  No reply │
├──────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐  │
│  │ Hi Aaron, just following up on my note last week.  │  │
│  │ Still think the timing is right — happy to keep    │  │
│  │ it brief if easier.                                │  │
│  └────────────────────────────────────────────────────┘  │
│  [Copy]  [Mark declined]  [Snooze 7d]  [Stop sequence]  │
└──────────────────────────────────────────────────────────┘
```

---

## No Auto-Send — Ever

The buttons are always:
- **Copy message** — copies to clipboard, fundraiser pastes into LinkedIn or Gmail
- **Open LinkedIn** — deep links to the contact's LinkedIn profile
- **Open Gmail** — opens a mailto: link with To, Subject, Body pre-filled

The message must come from the fundraiser's real account, not an API call.
Reasons: deliverability, platform ToS, trust, liability.

The system is a drafting and staging tool. The fundraiser is always the sender.

---

## Outreach Item Data Model

```python
{
  "contact_id":         "recXXX",
  "trigger_type":       "giving_signal_appeared",
  "trigger_detail":     "Posted about climate manufacturing 2 days ago",
  "trigger_strength":   "high",           # high / medium / low
  "channel":            "linkedin_inmail",
  "warm_path_contact":  "Jeremiah",       # null if no warm path
  "intro_strength":     "strong",         # null if no warm path
  "draft_message":      "...",
  "intro_draft":        "...",            # null if no warm path
  "status":             "queued",         # queued → sent → responded / declined / cooling
  "sent_at":            null,
  "followup_due_at":    null,
  "sequence_step":      1,               # 1 = initial, 2 = first follow-up, 3 = final touch
  "notes":              ""
}
```

---

## Contact Stage Lifecycle

`outreach_status` field in Airtable:

```
not_started → queued → contacted → responded → meeting_booked → donated
                                 ↘ declined → cooling (90 days) → not_started
```

---

## Sequence Cadence

1. Initial outreach
2. Follow-up at 10 days if no response
3. Final touch at 21 days
4. Cool-down: 90 days minimum before re-engaging

Fundraising sequences are short and personal — not sales cadences.

---

## UX Principles

1. **Context before message** — fundraiser sees why this person, why now, before seeing the draft
2. **Warm path surfaces first** — intro request is the primary action; cold message is the fallback
3. **Trigger gates cold outreach** — no trigger, no cold message queued
4. **One at a time** — not a list to blast through; deliberate, high-value contact
5. **Snooze matters** — fundraiser may want to wait; snoozed contact returns at the right moment
6. **System drafts, human sends** — HITL throughout, no exceptions

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

LangGraph nodes:
`prioritize → detect_trigger → select_channel → find_warm_path → draft → hitl_review → log_to_airtable → schedule_followup`

---

## Open Questions

- What signal threshold promotes a contact from cold → warm tier automatically?
- How is "org mission + current campaign" context injected into the drafter?
- Does the fundraiser configure their own voice examples, or does the system learn from approved messages over time?
- Where does sequence state live — Airtable fields or internal DB?
- How does the system handle a response that comes in — manual logging or email/LinkedIn integration?
