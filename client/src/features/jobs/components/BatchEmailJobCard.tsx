import type { BatchEmailJob } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { motion } from "framer-motion";
import { AlertTriangle, ChevronRight, FileText, Loader2, Pause, Play, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EMAIL_JOB_STATUS, TIER_META } from "../utils";

export interface BatchEmailJobCardProps {
    job: BatchEmailJob;
    onDelete: (job: BatchEmailJob) => void;
    deleting: boolean;
    onToggle?: (job: BatchEmailJob) => void;
    onTemplateClick?: (job: BatchEmailJob) => void;
}

// "Tomorrow morning" if retry_after is today; the actual time otherwise.
function fmtRetry(iso: string): string {
    const d = new Date(iso);
    const today = new Date();
    const sameDay = d.toDateString() === today.toDateString();
    return d.toLocaleString(undefined, {
        ...(sameDay ? {} : { weekday: "short", day: "numeric", month: "short" }),
        hour: "numeric", minute: "2-digit",
    });
}

export function BatchEmailJobCard({ job, onDelete, deleting, onToggle, onTemplateClick }: BatchEmailJobCardProps) {
    const navigate  = useNavigate();
    const tier      = TIER_META[job.tier]          ?? TIER_META.tier_1;
    const status    = EMAIL_JOB_STATUS[job.status] ?? EMAIL_JOB_STATUS.pending;
    const remaining = Math.max(0, job.total - job.sent - job.failed);
    const pct       = job.total > 0 ? Math.min(100, Math.round((job.sent / job.total) * 100)) : 0;
    const isActive  = job.status === "pending" || job.status === "running";
    // Auto-pause banner shows only when the runner paused the job because of
    // Gmail's quota (pause_reason='rate_limited'). Manual pauses get no banner
    // — the user knows why they pressed Pause.
    const isPaused = job.status === "paused";
    const autoPaused = isPaused && job.pause_reason === "rate_limited";
    // Pause/Resume only makes sense while the job hasn't finished yet.
    const canToggle = job.status === "running" || job.status === "pending" || job.status === "paused";

    const [pauseBannerDismissed, setPauseBannerDismissed] = useState(false);

    const goToDetail = () => navigate(`/outreach/batch-jobs/${job.id}`);
    const stopAndDo = (fn: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); fn(); };

    const stats = [
        { label: "Total",     value: job.total,   color: "text-foreground/70"  },
        { label: "Sent",      value: job.sent,    color: "text-primary/80"     },
        { label: "Failed",    value: job.failed,  color: job.failed > 0 ? "text-red-400/80" : "text-muted-foreground/30" },
        { label: "Remaining", value: remaining,   color: isActive ? "text-primary/60" : "text-muted-foreground/30" },
    ];

    return (
        <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
        >
            <Card
                className="overflow-hidden w-full rounded-md cursor-pointer hover:border-white/15 transition-colors"
                onClick={goToDetail}
            >

                {/* Header */}
                <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/50">
                    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-[11px] font-medium shrink-0", tier.badge)}>
                        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", tier.dot)} />
                        {tier.label}
                    </span>
                    <span className="text-sm font-mono text-foreground/75 truncate flex-1 min-w-0">{job.campaign_goal}</span>
                    <span className="text-[11px] font-mono text-muted-foreground/40 shrink-0">
                        {new Date(job.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    </span>
                    {onToggle && canToggle && (
                        <button
                            onClick={stopAndDo(() => onToggle(job))}
                            title={isPaused ? "Resume" : "Pause"}
                            className="p-1 rounded transition-colors shrink-0 hover:bg-muted hover:text-foreground text-muted-foreground/50 cursor-pointer"
                        >
                            {isPaused ? <Play size={13} /> : <Pause size={13} />}
                        </button>
                    )}
                    <button
                        onClick={stopAndDo(() => onDelete(job))}
                        disabled={deleting}
                        className="p-1 rounded transition-colors shrink-0 hover:bg-red-500/10 hover:text-red-400 text-muted-foreground/30 cursor-pointer"
                    >
                        {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                    </button>
                </div>

                {/* Auto-pause banner — visible only when the runner auto-paused
                    because of Gmail's daily quota. Manual pauses are silent. */}
                {autoPaused && !pauseBannerDismissed && (
                    <div className="flex items-start gap-3 px-4 py-2.5 border-b border-amber-500/20 bg-amber-500/5">
                        <AlertTriangle size={13} className="text-amber-400 shrink-0 mt-0.5" />
                        <p className="flex-1 text-[11px] font-mono text-amber-300/85 leading-relaxed">
                            Auto-paused — Gmail hit its daily send quota.{" "}
                            {job.retry_after ? (
                                <>Resume manually after <span className="font-semibold text-amber-200">{fmtRetry(job.retry_after)}</span>.</>
                            ) : (
                                <>Resume manually once the quota window resets (usually next morning).</>
                            )}
                        </p>
                        <button
                            onClick={stopAndDo(() => setPauseBannerDismissed(true))}
                            className="text-amber-400/40 hover:text-amber-400 transition-colors shrink-0"
                        >
                            <X size={12} />
                        </button>
                    </div>
                )}

                {/* Progress + stats */}
                <div className="px-4 pt-4 pb-3">
                    <div className="h-1 rounded-full bg-muted overflow-hidden mb-1.5">
                        <motion.div
                            className="h-full bg-primary rounded-full"
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.6, ease: "easeOut" }}
                        />
                    </div>
                    <div className="flex items-center gap-4 text-sm mb-4">
                        <span className="font-semibold tabular-nums text-foreground">
                            {job.sent.toLocaleString()}
                            {job.total > 0 && (
                                <span className="text-muted-foreground">/{job.total.toLocaleString()} ({pct}%)</span>
                            )}
                        </span>
                        <span className="text-primary/70 tabular-nums">✓ {job.sent}</span>
                        <span className="text-muted-foreground tabular-nums">— {remaining}</span>
                        {job.failed > 0 && <span className="text-red-400/80 tabular-nums">✗ {job.failed}</span>}
                        <div className="ml-auto flex items-center gap-1.5">
                            <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", status.dot)} />
                            <span className={cn("text-xs", status.text)}>{status.label}</span>
                        </div>
                    </div>
                    <div className="grid grid-cols-4 divide-x divide-border/50 rounded-lg border border-border/50 bg-muted/20 overflow-hidden">
                        {stats.map((s) => (
                            <div key={s.label} className="flex flex-col items-center py-4 gap-1">
                                <span className="font-mono text-[10px] text-muted-foreground/50 tracking-widest uppercase">
                                    {s.label}
                                </span>
                                <span className={cn("text-2xl font-bold tabular-nums leading-none", s.color)}>
                                    {s.value.toLocaleString()}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Template link */}
                <div className="px-4 py-2 border-t border-border/40">
                    {onTemplateClick ? (
                        <button
                            onClick={stopAndDo(() => onTemplateClick(job))}
                            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground/50 hover:text-primary transition-colors group"
                        >
                            <FileText size={10} className="group-hover:text-primary/60 transition-colors shrink-0" />
                            <span className="font-mono">Template #{job.template_id}</span>
                            <ChevronRight size={9} className="group-hover:text-primary/50 transition-colors" />
                        </button>
                    ) : (
                        <Link
                            to={`/outreach?campaign_id=${job.campaign_id}&tier=${job.tier}`}
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground/50 hover:text-primary transition-colors group"
                        >
                            <FileText size={10} className="group-hover:text-primary/60 transition-colors shrink-0" />
                            <span className="font-mono">Template #{job.template_id}</span>
                            <ChevronRight size={9} className="group-hover:text-primary/50 transition-colors" />
                        </Link>
                    )}
                </div>
            </Card>
        </motion.div>
    );
}
