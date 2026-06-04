import { Globe, Mail, Users } from "lucide-react";
import type { Tier } from "./types";

export const PAGE_SIZE = 50;

export const container = {
    hidden: {},
    show: { transition: { staggerChildren: 0.06 } },
};

export const item = {
    hidden: { opacity: 0, y: 10 },
    show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

export const TIER_CONFIG: Record<
    Tier,
    {
        label: string;
        color: string;
        dot: string;
        icon: React.ElementType;
        description: string;
    }
> = {
    tier_1: {
        label: "Tier 1",
        color: "bg-blue-500",
        dot: "bg-blue-500",
        icon: Users,
        description: "Highest signal — strong giving indicators and wealth trajectory",
    },
    tier_2: {
        label: "Tier 2",
        color: "bg-violet-500",
        dot: "bg-violet-500",
        icon: Mail,
        description: "Mid signal — moderate indicators, personalised direct outreach",
    },
    tier_3: {
        label: "Tier 3",
        color: "bg-zinc-500",
        dot: "bg-zinc-500",
        icon: Globe,
        description: "Lower signal — broader reach, lower certainty",
    },
};

export const CAMPAIGN_STATUS_COLOR: Record<string, string> = {
    ready: "bg-teal-300",
    in_progress: "bg-blue-500",
    segmenting: "bg-amber-500",
    failed: "bg-red-500",
    draft: "bg-muted-foreground/40",
    completed: "bg-muted-foreground/40",
};

export const TIER_ROWS = [
    {
        key: "tier_1" as Tier,
        label: "Tier 1",
        dot: "bg-blue-500",
        bar: "bg-blue-500",
        text: "text-blue-400",
        badge: "bg-blue-500/10 text-blue-400 border border-blue-500/25",
        hex: "#3b82f6",
        desc: "Highest signal contacts — strong giving indicators and wealth trajectory",
    },
    {
        key: "tier_2" as Tier,
        label: "Tier 2",
        dot: "bg-violet-500",
        bar: "bg-violet-500",
        text: "text-violet-400",
        badge: "bg-violet-500/10 text-violet-400 border border-violet-500/25",
        hex: "#8b5cf6",
        desc: "Mid-signal contacts — moderate indicators, personalised direct outreach",
    },
    {
        key: "tier_3" as Tier,
        label: "Tier 3",
        dot: "bg-slate-400",
        bar: "bg-slate-400",
        text: "text-slate-400",
        badge: "bg-slate-500/10 text-slate-400 border border-slate-500/25",
        hex: "#94a3b8",
        desc: "Lower-signal contacts — broader reach, lower certainty",
    },
];

export const SIGNAL_META = [
    { key: "giving", label: "Giving", color: "#818cf8" },
    { key: "wealth", label: "Wealth", color: "#38bdf8" },
    { key: "capacity", label: "Capacity", color: "#34d399" },
    { key: "trajectory", label: "Trajectory", color: "#fbbf24" },
    { key: "topics", label: "Topics", color: "#94a3b8" },
    { key: "personality", label: "Personality", color: "#c084fc" },
    { key: "engagement", label: "Engagement", color: "#fb923c" },
];

export const WHEEL_SEGS = [
    { label: "Giving", key: "post_signal", color: "#818cf8", short: "Giving" },
    { label: "Warm Path", key: "warm_path", color: "#a78bfa", short: "Warm" },
    { label: "Match", key: "rag", color: "#22d3ee", short: "Match" },
    { label: "Capacity", key: "capacity", color: "#34d399", short: "Cap" },
    { label: "Trajectory", key: "trajectory", color: "#fbbf24", short: "Traj" },
    { label: "Topics", key: "topics", color: "#94a3b8", short: "Topics" },
    { label: "Engagement", key: "engagement", color: "#fb923c", short: "Eng" },
];

export const KNOWN_FIELDS: Record<string, string> = {
    // Contact inputs — read from user's Airtable, never written by us
    first_name:            "Contact",
    company:               "Contact",
    title:                 "Contact",

    // LinkedIn profile — extracted from scraped profile data (always written by pipeline)
    last_three_roles:      "LinkedIn",   // pure data: last 3 roles from experience array
    trajectory_tag:        "LinkedIn",   // LLM: career archetype classification
    trajectory_signal:     "LinkedIn",   // LLM: one-sentence explanation of trajectory

    // Post signals — derived from LinkedIn posts analysis (always written by pipeline)
    post_wealth_signal:    "Posts",      // LLM: wealth/liquidity signals in posts
    post_giving_signal:    "Posts",      // LLM: philanthropic signals in posts
    post_topic_themes:     "Posts",      // LLM: recurring post topic categories
    post_engagement_tier:  "Posts",      // data: High / Medium / Low based on likes+comments
    post_personality_type: "Posts",      // LLM: thought_leader / curator / self_promoter / passive
    post_last_active:      "Posts",      // data: date of most recent post (YYYY-MM-DD)

    // News — derived from Google News search (written when ENRICH_NEWS=true)
    press_count:           "News",
    top_outlets:           "News",
    press_flags:           "News",
    notable_headline:      "News",

    // Warm path — computed from network matching
    warm_path_top_bridge:  "Warm path",  // name of best bridge contact
    warm_path_evidence:    "Warm path",  // top connection paths, one per line
    warm_opener:           "Warm path",  // send-time: "Through [bridge]," opener

    // Outreach signals — computed at send-time by the variable resolver
    topic_hook:            "Signals",    // "given your interest in [topics]"
    giving_reference:      "Signals",    // "your past support of [causes]"
    capacity_close:        "Signals",    // "a leadership-level gift" / "a contribution at any level"
};

export const FIELD_GROUPS: Record<string, string[]> = {
    Contact:     ["first_name", "company", "title"],
    LinkedIn:    ["last_three_roles", "trajectory_tag", "trajectory_signal"],
    Posts:       ["post_wealth_signal", "post_giving_signal", "post_topic_themes", "post_engagement_tier", "post_personality_type", "post_last_active"],
    News:        ["press_count", "top_outlets", "press_flags", "notable_headline"],
    "Warm path": ["warm_path_top_bridge", "warm_path_evidence", "warm_opener"],
    Signals:     ["topic_hook", "giving_reference", "capacity_close"],
};

export const SLOT_RE =
    /\[[A-Za-z][A-Za-z0-9 _/.-]*(?:\s*\|\s*fallback:\s*"[^"]*")?\]/g;

// Fields written by our pipeline that should NOT appear as template variables
// (internal artifacts, raw JSON blobs, numeric scores, timestamps)
export const ENRICHED_BLOCKLIST = new Set([
    "career_json",
    "post_analyzed_links",
    "warm_path_score",
    "warm_path_computed_at",
    "linkedin_candidates",
    "match_confidence",
    "match_source",
    "last_enriched",
    "enrichment_status",
]);
