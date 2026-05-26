import type { Batch } from "@/shared/api/client";

export interface Agg {
    processed: number;
    hits: number;
    misses: number;
    failed: number;
}

export function agg(batches: Batch[]): Agg {
    return batches.reduce(
        (a, b) => ({
            processed: a.processed + (b.processed ?? 0),
            hits:      a.hits      + (b.hits      ?? 0),
            misses:    a.misses    + (b.misses     ?? 0),
            failed:    a.failed    + (b.failed     ?? 0),
        }),
        { processed: 0, hits: 0, misses: 0, failed: 0 },
    );
}

export const BATCH_PRESETS = [100, 200, 300] as const;

export const batchDot: Record<string, string> = {
    pending:   "bg-muted-foreground",
    running:   "bg-primary/80 animate-pulse",
    completed: "bg-primary",
    failed:    "bg-red-500",
};

export const TIER_META: Record<string, { label: string; dot: string; bar: string; badge: string }> = {
    tier_1: { label: "Tier 1", dot: "bg-blue-500",   bar: "bg-blue-500",   badge: "bg-blue-500/10 text-blue-400 border border-blue-500/25"     },
    tier_2: { label: "Tier 2", dot: "bg-violet-500", bar: "bg-violet-500", badge: "bg-violet-500/10 text-violet-400 border border-violet-500/25" },
    tier_3: { label: "Tier 3", dot: "bg-slate-400",  bar: "bg-slate-400",  badge: "bg-slate-500/10 text-slate-400 border border-slate-500/25"   },
};

export const EMAIL_JOB_STATUS: Record<string, { label: string; dot: string; text: string }> = {
    pending:   { label: "Queued",    dot: "bg-amber-400",                text: "text-amber-400"  },
    running:   { label: "Sending",   dot: "bg-primary/70 animate-pulse", text: "text-primary/80" },
    completed: { label: "Completed", dot: "bg-primary",                  text: "text-primary"    },
    failed:    { label: "Failed",    dot: "bg-red-500",                  text: "text-red-400"    },
};
