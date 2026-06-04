import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, BarChart3, Check, Database, Loader2, Save, Sparkles } from "lucide-react";
import { useOutreachContext } from "../context/OutreachContext";
import { sentenceCase } from "../utils";

// Pipeline stages, in order. `step` values come from the backend events.
const STAGES = [
    { key: "load", label: "Loading contacts", Icon: Database },
    { key: "rag", label: "Semantic relevance", Icon: Sparkles },
    { key: "finalize", label: "Scoring & tiering", Icon: BarChart3 },
    { key: "persist", label: "Saving results", Icon: Save },
] as const;

const STEP_ORDER: Record<string, number> = { load: 0, rag: 1, finalize: 2, persist: 3 };

const WEIGHT_LABELS: Record<string, string> = {
    warm_path: "Warm path",
    post_signal: "Giving signal",
    rag: "Goal match",
    capacity: "Capacity",
    trajectory: "Trajectory",
    topics: "Topics",
    engagement: "Engagement",
};

const TIER_META = [
    { key: "tier_1" as const, label: "Tier 1", sub: "Warmest", color: "bg-teal-300", text: "text-teal-300" },
    { key: "tier_2" as const, label: "Tier 2", sub: "Solid", color: "bg-blue-500", text: "text-blue-400" },
    { key: "tier_3" as const, label: "Tier 3", sub: "Broader", color: "bg-muted-foreground/40", text: "text-muted-foreground" },
];

export function SegmentingView() {
    const { activeCampaign, segEvents } = useOutreachContext();

    // Derive pipeline state from the event stream
    const complete = segEvents.some((e) => e.type === "complete");
    const error = segEvents.find((e) => e.type === "error");

    let maxStep = -1;
    const msgByStep: Record<string, string> = {};
    let count: number | undefined;
    let indexed: number | undefined;
    let total: number | undefined;
    let goalWeights: Record<string, number> | undefined;
    let tierCounts: { tier_1: number; tier_2: number; tier_3: number } | undefined;
    let warning: string | undefined;

    for (const e of segEvents) {
        if (e.step && e.step in STEP_ORDER) {
            maxStep = Math.max(maxStep, STEP_ORDER[e.step]);
            msgByStep[e.step] = e.message;
        }
        if (e.count != null) count = e.count;
        if (e.indexed != null) indexed = e.indexed;
        if (e.total != null) total = e.total;
        if (e.goal_weights) goalWeights = e.goal_weights;
        if (e.tier_counts) tierCounts = e.tier_counts;
        if (e.type === "warning") warning = e.message;
    }

    const stageStatus = (idx: number): "done" | "active" | "pending" => {
        if (complete) return "done";
        if (idx < maxStep) return "done";
        if (idx === maxStep) return "active";
        return "pending";
    };

    const tierTotal = tierCounts ? tierCounts.tier_1 + tierCounts.tier_2 + tierCounts.tier_3 : 0;
    const weightEntries = goalWeights
        ? Object.entries(goalWeights).sort((a, b) => b[1] - a[1]).slice(0, 5)
        : [];
    const maxWeight = weightEntries.length ? weightEntries[0][1] : 1;

    return (
        <div className="p-6 max-w-xl space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    {complete ? (
                        <Check size={15} className="text-teal-300" />
                    ) : error ? (
                        <AlertTriangle size={15} className="text-red-400" />
                    ) : (
                        <Loader2 size={15} className="animate-spin text-primary" />
                    )}
                </div>
                <div className="min-w-0">
                    <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground/60 mb-0.5">
                        {complete ? "Segmented" : error ? "Failed" : "Segmenting"}
                    </p>
                    <p className="text-sm text-foreground/70 truncate">{sentenceCase(activeCampaign?.goal ?? "")}</p>
                </div>
            </div>

            {/* Stepper */}
            <div className="space-y-1">
                {STAGES.map((stage, idx) => {
                    const status = stageStatus(idx);
                    const isActive = status === "active";
                    const isDone = status === "done";

                    // Per-stage metric line
                    let metric = "";
                    if (stage.key === "load" && count != null) metric = `${count.toLocaleString()} contacts`;
                    else if (stage.key === "rag" && indexed != null && total != null) metric = `${indexed.toLocaleString()} / ${total.toLocaleString()} indexed`;
                    else if (stage.key === "finalize" && tierCounts) metric = `${tierTotal.toLocaleString()} scored`;

                    return (
                        <div key={stage.key} className="flex items-start gap-3">
                            {/* Rail */}
                            <div className="flex flex-col items-center self-stretch">
                                <div className={cn(
                                    "h-7 w-7 rounded-full flex items-center justify-center shrink-0 transition-colors border",
                                    isDone ? "bg-teal-300/15 border-teal-300/30 text-teal-300"
                                        : isActive ? "bg-primary/15 border-primary/40 text-primary"
                                        : "bg-muted/20 border-border/40 text-muted-foreground/30",
                                )}>
                                    {isDone ? <Check size={13} />
                                        : isActive ? <Loader2 size={13} className="animate-spin" />
                                        : <stage.Icon size={13} />}
                                </div>
                                {idx < STAGES.length - 1 && (
                                    <div className={cn(
                                        "w-px flex-1 my-1 min-h-4 transition-colors",
                                        isDone ? "bg-teal-300/30" : "bg-border/40",
                                    )} />
                                )}
                            </div>
                            {/* Label + live message */}
                            <div className="pt-1 pb-2 min-w-0 flex-1">
                                <div className="flex items-center justify-between gap-2">
                                    <span className={cn(
                                        "text-sm transition-colors",
                                        isDone ? "text-foreground/80" : isActive ? "text-foreground font-medium" : "text-muted-foreground/40",
                                    )}>
                                        {stage.label}
                                    </span>
                                    {metric && (
                                        <span className="text-[11px] font-mono text-muted-foreground/50 shrink-0">{metric}</span>
                                    )}
                                </div>
                                <AnimatePresence>
                                    {isActive && msgByStep[stage.key] && (
                                        <motion.p
                                            initial={{ opacity: 0, height: 0 }}
                                            animate={{ opacity: 1, height: "auto" }}
                                            exit={{ opacity: 0, height: 0 }}
                                            className="text-[11px] font-mono text-muted-foreground/50 mt-0.5 truncate"
                                        >
                                            {msgByStep[stage.key]}
                                        </motion.p>
                                    )}
                                </AnimatePresence>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Adaptive weights — "the AI tuned itself to your goal" */}
            <AnimatePresence>
                {weightEntries.length > 0 && !complete && (
                    <motion.div
                        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                        className="rounded-lg border border-border/40 bg-muted/10 p-4 space-y-2.5"
                    >
                        <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/50">
                            Ranking tuned to your goal
                        </p>
                        {weightEntries.map(([key, w]) => (
                            <div key={key} className="flex items-center gap-3">
                                <span className="text-[11px] text-muted-foreground/70 w-24 shrink-0">
                                    {WEIGHT_LABELS[key] ?? key}
                                </span>
                                <div className="flex-1 h-1.5 rounded-full bg-muted/40 overflow-hidden">
                                    <motion.div
                                        className="h-full rounded-full bg-primary/50"
                                        initial={{ width: 0 }}
                                        animate={{ width: `${(w / maxWeight) * 100}%` }}
                                        transition={{ duration: 0.5, ease: "easeOut" }}
                                    />
                                </div>
                                <span className="text-[10px] font-mono text-muted-foreground/40 w-9 text-right shrink-0">
                                    {Math.round(w * 100)}%
                                </span>
                            </div>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Tier result — the satisfying payoff */}
            <AnimatePresence>
                {tierCounts && (
                    <motion.div
                        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                        className="rounded-lg border border-border/40 bg-card p-4 space-y-3"
                    >
                        <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/50">
                            {complete ? "Tiers assigned" : "Tiers forming"}
                        </p>
                        {TIER_META.map(({ key, label, sub, color, text }, i) => {
                            const n = tierCounts![key];
                            const pct = tierTotal > 0 ? (n / tierTotal) * 100 : 0;
                            return (
                                <div key={key} className="space-y-1">
                                    <div className="flex items-center justify-between text-[11px]">
                                        <span className={cn("font-medium", text)}>{label} <span className="text-muted-foreground/40">· {sub}</span></span>
                                        <span className="font-mono text-muted-foreground/60">{n.toLocaleString()}</span>
                                    </div>
                                    <div className="h-1.5 rounded-full bg-muted/30 overflow-hidden">
                                        <motion.div
                                            className={cn("h-full rounded-full", color)}
                                            initial={{ width: 0 }}
                                            animate={{ width: `${pct}%` }}
                                            transition={{ duration: 0.5, delay: i * 0.08, ease: "easeOut" }}
                                        />
                                    </div>
                                </div>
                            );
                        })}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Warning (e.g. no embeddings) */}
            {warning && !complete && (
                <div className="flex items-start gap-2 rounded-md border border-amber-500/25 bg-amber-500/8 px-3 py-2.5">
                    <AlertTriangle size={12} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-[11px] font-mono text-amber-400/80 leading-relaxed">{warning}</p>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="flex items-start gap-2 rounded-md border border-red-500/25 bg-red-500/8 px-3 py-2.5">
                    <AlertTriangle size={12} className="text-red-400 shrink-0 mt-0.5" />
                    <p className="text-[11px] font-mono text-red-400/80 leading-relaxed">{error.message}</p>
                </div>
            )}

            {/* Complete footer */}
            {complete && (
                <motion.div
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    className="flex items-center gap-2 text-xs text-teal-300 font-mono"
                >
                    <Check size={13} /> Complete — loading tiers…
                </motion.div>
            )}
        </div>
    );
}
