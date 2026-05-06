"""
Generate May 2026 team plan PDF — clean readable format.
Usage: python scripts/generate_may_plan.py
Output: docs/may_2026_team_plan.pdf
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "may_2026_team_plan.pdf")
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

styles = getSampleStyleSheet()

title    = ParagraphStyle("title",    parent=styles["Normal"], fontSize=22, fontName="Helvetica-Bold", spaceAfter=6)
h1       = ParagraphStyle("h1",       parent=styles["Normal"], fontSize=14, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4)
h2       = ParagraphStyle("h2",       parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=3)
h3       = ParagraphStyle("h3",       parent=styles["Normal"], fontSize=10, fontName="Helvetica-BoldOblique", spaceBefore=8, spaceAfter=2, textColor=colors.HexColor("#374151"))
body     = ParagraphStyle("body",     parent=styles["Normal"], fontSize=10, fontName="Helvetica",      spaceAfter=5,  leading=15)
bullet   = ParagraphStyle("bullet",   parent=styles["Normal"], fontSize=10, fontName="Helvetica",      spaceAfter=4,  leading=14, leftIndent=12, bulletIndent=0)
sub      = ParagraphStyle("sub",      parent=styles["Normal"], fontSize=9,  fontName="Helvetica-Oblique", spaceAfter=3, leading=13, leftIndent=12, textColor=colors.HexColor("#6B7280"))
meta     = ParagraphStyle("meta",     parent=styles["Normal"], fontSize=10, fontName="Helvetica-Oblique", spaceAfter=12, textColor=colors.HexColor("#6B7280"))

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB"), spaceAfter=6, spaceBefore=2)

def build():
    doc = SimpleDocTemplate(OUTPUT, pagesize=A4,
                            leftMargin=22*mm, rightMargin=22*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    s = []

    # Title
    s.append(Paragraph("May 2026 Team Plan", title))
    s.append(Paragraph("Phase 1: Contact Intelligence  |  Emmanuel, Jeremiah, Abdulazeez", meta))
    s.append(hr())

    # Goal
    s.append(Paragraph("Central Goal", h1))
    s.append(Paragraph(
        "Turn a flat contact list into a ranked, intelligence-backed prospect pipeline. "
        "Every contact enriched in May has a wealth score, a career archetype, at least one financial signal, "
        "and a warm introduction path. Fundraiser prep time drops from 30 minutes per contact to under 5.",
        body))
    s.append(hr())

    # Weeks
    weeks = [
        {
            "title": "Week 1 — Stabilise & Ship  (May 5-9)",
            "theme": "Get the live pipeline running clean and validate what is already built.",
            "members": [
                ("Emmanuel", [
                    ("Restart server + resume Job 2 enrichment run",
                     "All code fixes are in. Restart via run_py312.bat, resume Job 2, monitor first 3 batches. Target: under 5% failure rate."),
                    ("Backfill news signals on all completed batches",
                     "Run python scripts/backfill_news_signals.py for every completed batch. Confirm press_count is in Airtable."),
                ]),
                ("Jeremiah", [
                    ("Secure Crunchbase Pro API key",
                     "Sign up, run a test call against a known contact, confirm the /entities/people endpoint returns investment and exit data."),
                    ("Confirm Arkham Intelligence API access",
                     "Apply for Arkham or confirm Nansen as fallback. If neither accessible by May 9, escalate immediately — this blocks Week 3."),
                ]),
                ("Abdulazeez", [
                    ("QA 20 enriched records — validate trajectory and post signals",
                     "Pick 20 contacts from the completed batch. Check trajectory_tag matches career history. Log misclassifications in a shared doc."),
                    ("Audit CRM for contact_type field + crypto contact count",
                     "Check if contact_type exists in Airtable. Add it if missing. Count crypto-tagged contacts — this scopes Week 3 onchain work."),
                ]),
            ],
        },
        {
            "title": "Week 2 — Financial Signals  (May 12-16)",
            "theme": "Add Crunchbase as a second financial data source and ship the first composite wealth score.",
            "members": [
                ("Emmanuel", [
                    ("Define and document wealth scoring weights",
                     "Write the scoring rubric before the scorer is built. Assign weights per signal (e.g. EXITED_FOUNDER = +30, Crunchbase exit = +25). Share by May 13."),
                    ("Mid-week Crunchbase review and unblock",
                     "Check in with Jeremiah on May 14. Review field output on 5 test contacts. Sign off before it goes into the pipeline."),
                ]),
                ("Jeremiah", [
                    ("Build crunchbase_client.py and parse 5 CRM fields",
                     "Wrap the Crunchbase Pro API, resolve person entities from URLs. Parse: total_investments, notable_exits, portfolio_companies, co_investors, recent_funding_activity. Nulls must not crash the pipeline."),
                    ("Wire Crunchbase into BatchExecutor and add Airtable fields",
                     "Integrate as a parallel gather call. Create the 5 fields in Airtable via script. Test on 20 contacts and confirm hit rate."),
                ]),
                ("Abdulazeez", [
                    ("Build wealth_scorer.py — composite confidence score",
                     "Aggregate all signals into wealth_confidence (High / Medium / Low) using the weights Emmanuel defines. Output a signal_trail JSON showing what contributed."),
                    ("Add wealth_confidence and signal_trail to Airtable and wire into pipeline",
                     "Create both fields via script. Wire scorer as the final step in _process_record. Confirm populated on 10 test contacts."),
                ]),
            ],
        },
        {
            "title": "Week 3 — Deep Wealth  (May 19-23)",
            "theme": "Add onchain wealth verification for crypto-native contacts.",
            "members": [
                ("Emmanuel", [
                    ("Collect all 3 Sales Navigator exports",
                     "All team members export their LinkedIn connections as CSV before May 21. Week 4 is fully blocked without these files."),
                    ("Validate wealth scoring output against known HNW contacts",
                     "Pick 10 contacts you know are high net worth. Check scorer assigned them High confidence. Document any gaps for calibration."),
                ]),
                ("Jeremiah", [
                    ("Build arkham_client.py — entity search and wallet resolution",
                     "Take name and company, return a wallet address with confidence score. Low-confidence matches must not auto-write to the CRM."),
                    ("Build holdings aggregator and conditional execution gate",
                     "Fetch token balances, convert to USD. Gate fires only when contact_type is crypto. Test on 10 known crypto contacts. Wire 4 onchain fields to Airtable."),
                ]),
                ("Abdulazeez", [
                    ("Update wealth scorer to include onchain signals",
                     "Extend wealth_scorer.py so a confirmed wallet balance above threshold pushes a contact to High confidence regardless of other signals."),
                    ("Full scoring QA on 15 contacts across all types",
                     "Run the full pipeline on tech founders, finance execs, and crypto-native contacts. Document any scoring anomalies."),
                ]),
            ],
        },
        {
            "title": "Week 4 — Network Intelligence  (May 26-31)",
            "theme": "Build warm path mapping — turn team LinkedIn networks into ranked introduction routes for every prospect.",
            "members": [
                ("Emmanuel", [
                    ("Build network_mapper.py — team graph and prospect adjacency",
                     "Parse and deduplicate the 3 Sales Navigator exports. For each CRM prospect, find which team member is connected and at what depth."),
                    ("Lead Phase 1 retrospective and draft Phase 2 scope",
                     "Run a team retro on signal usefulness and calibration. Draft the Phase 2 outreach automation scope for June."),
                ]),
                ("Jeremiah", [
                    ("Support network graph deduplication",
                     "Three exports will have overlapping connections. Build the deduplication pass that merges duplicate profiles into single nodes in the team graph."),
                    ("Document Sales Navigator refresh cadence",
                     "Write the standing operating procedure: how often to re-export (weekly), how to run the refresh, what changes between runs."),
                ]),
                ("Abdulazeez", [
                    ("Build intro strength scoring",
                     "Score each prospect-team connection by recency, shared interactions, and mutual connections. Distinguishes a genuine warm intro from a name-only connection."),
                    ("Wire warm path fields into Airtable and validate",
                     "Add mutual_connections, top_introducer, intro_strength_score to Airtable. Test against 5 known real warm paths in the existing network."),
                ]),
            ],
        },
    ]

    for week in weeks:
        s.append(Paragraph(week["title"], h1))
        s.append(Paragraph(week["theme"], body))
        for name, tasks in week["members"]:
            s.append(Paragraph(name, h2))
            for task_title, task_desc in tasks:
                s.append(Paragraph(f"- {task_title}", bullet))
                s.append(Paragraph(task_desc, sub))
        s.append(hr())

    # KPIs
    s.append(Paragraph("May 2026 KPIs", h1))
    s.append(Paragraph("Goals", h2))

    goals = [
        (
            "Build and deploy a full contact intelligence pipeline that enriches every prospect with career, financial, and behavioural signals automatically.",
            [
                "Job 2 completes all 37 batches with under 5% failure rate after retries.",
                "80% or more of contacts have at least 3 intelligence fields populated by month end.",
                "All 7 enrichment signals live in production by May 31: trajectory, news, posts, Crunchbase, onchain, warm path, and wealth score.",
            ]
        ),
        (
            "Integrate all enriched signals directly into Airtable CRM so the fundraising team can act on intelligence without leaving their existing workflow.",
            [
                "wealth_confidence field assigned to 100% of enriched contacts by end of Week 2.",
                "press_count populated for 60% or more of enriched contacts.",
                "Warm path fields visible in Airtable for 30% or more of the prospect list.",
            ]
        ),
        (
            "Improve pipeline reliability and data accuracy so enrichment results can be trusted as a basis for fundraising decisions.",
            [
                "trajectory_tag misclassification rate below 10% on a spot-check of 20 records.",
                "Onchain wealth estimates within 15% of public wallet trackers. Zero false matches written to CRM without human review.",
                "Crunchbase hit rate of 40% or more on contacts with a known Crunchbase URL.",
            ]
        ),
        (
            "Build a relationship intelligence system that consolidates contacts across platforms, maps them into a network graph, and surfaces automated warm introduction recommendations.",
            [
                "Warm introduction path found for 30% or more of CRM contacts.",
                "Fundraiser contact prep time drops from 30 minutes to under 5 minutes, validated by a live review of the top 10 prospects before May 31.",
            ]
        ),
    ]

    for goal_text, metrics in goals:
        s.append(Paragraph(goal_text, body))
        for m in metrics:
            s.append(Paragraph(f"- {m}", bullet))
        s.append(Spacer(1, 8))

    doc.build(s)
    print(f"PDF saved -> {OUTPUT}")

if __name__ == "__main__":
    build()
