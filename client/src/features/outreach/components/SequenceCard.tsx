import { type Sequence } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { AlertTriangle, Clock, Layers, Pause, Play, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { TIER_ROWS } from "../constants";
import { sentenceCase } from "../utils";

// Exact local time, e.g. "Wed, 28 May, 9:14 AM"
function fmtAbs(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
        weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
    });
}

// Human relative hint from now: "any moment" | "in 12m" | "in 3h" | "in 2d"
function fmtRel(iso: string): string {
    const ms = new Date(iso).getTime() - Date.now();
    if (ms <= 60_000) return "any moment";
    const mins = Math.round(ms / 60_000);
    if (mins < 60) return `in ${mins}m`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `in ${hrs}h`;
    return `in ${Math.round(hrs / 24)}d`;
}

const STATUS_STYLE: Record<string, string> = {
    active:    "text-teal-300 bg-teal-300/10 border-teal-300/25",
    paused:    "text-amber-400 bg-amber-500/10 border-amber-500/25",
    draft:     "text-muted-foreground bg-muted/40 border-border/40",
    completed: "text-blue-400 bg-blue-500/10 border-blue-500/25",
};

/**
 * Sequence summary card — at-a-glance metrics + status + next-send.
 *
 * The whole card is clickable: navigates to the per-sequence detail view at
 * /outreach/sequences/:id, where the full engagement analytics live (who
 * clicked, who replied, who bounced, the step timeline, etc.).
 *
 * Pause/delete buttons stay actionable inline — their click handlers
 * stopPropagation so they don't also trigger navigation.
 */
export function SequenceCard({ seq, onToggle, onDelete }: { seq: Sequence; onToggle: (s: Sequence) => void; onDelete: (s: Sequence) => void }) {
    const navigate = useNavigate();
    const tierCfg = TIER_ROWS.find((r) => r.key === seq.tier);
    const s = seq.stats ?? { total: 0, active: 0, replied: 0, completed: 0, stopped: 0, bounced: 0, by_step: {} };
    const stepCount = seq.steps?.length ?? Math.max(1, Object.keys(s.by_step).length);
    const canToggle = seq.status === "active" || seq.status === "paused";
    const clickedCount = s.unique_clickers ?? 0;

    const metrics = [
        { label: "Active",  value: s.active,    color: "text-primary" },
        { label: "Clicked", value: clickedCount, color: clickedCount > 0 ? "text-primary" : "text-muted-foreground/50" },
        { label: "Replied", value: s.replied,   color: s.replied > 0 ? "text-teal-300" : "text-muted-foreground/50" },
        { label: "Done",    value: s.completed, color: "text-muted-foreground/70" },
        { label: "Bounced", value: s.bounced,   color: s.bounced > 0 ? "text-red-500/75" : "text-muted-foreground/50" },
        { label: "Stopped", value: s.stopped,   color: s.stopped > 0 ? "text-amber-500/70" : "text-muted-foreground/50" },
    ];

    // High-bounce-rate warning. Once 5+ contacts have been actually sent to, if
    // ≥5% of them bounce, warn the fundraiser so they can pause + clean the list
    // before sender reputation suffers further.
    const reached = s.completed + s.replied + s.stopped + s.bounced + s.active;
    const bounceRate = reached >= 5 && s.bounced > 0 ? (s.bounced / reached) : 0;
    const showBounceWarning = bounceRate >= 0.05;

    const goToDetail = () => navigate(`/outreach/sequences/${seq.id}`);
    const stopAndDo = (fn: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); fn(); };

    return (
        <Card
            className="overflow-hidden w-full cursor-pointer hover:border-border/80 transition-colors"
            onClick={goToDetail}
        >
            <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/60">
                {tierCfg && (
                    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-[11px] font-medium shrink-0", tierCfg.badge)}>
                        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", tierCfg.dot)} />
                        {tierCfg.label}
                    </span>
                )}
                <span className="inline-flex items-center gap-1 text-[11px] font-mono text-muted-foreground/50 shrink-0">
                    <Layers size={11} /> {stepCount} step{stepCount !== 1 ? "s" : ""}
                </span>
                <span className="text-xs text-muted-foreground/60 font-mono truncate flex-1 min-w-0">
                    {seq.campaign_goal ? sentenceCase(seq.campaign_goal) : seq.name}
                </span>
                <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-wide shrink-0", STATUS_STYLE[seq.status] ?? STATUS_STYLE.draft)}>
                    {seq.status}
                </span>
                {canToggle && (
                    <button
                        onClick={stopAndDo(() => onToggle(seq))}
                        title={seq.status === "active" ? "Pause" : "Resume"}
                        className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/50 hover:text-foreground hover:bg-muted transition-colors shrink-0"
                    >
                        {seq.status === "active" ? <Pause size={12} /> : <Play size={12} />}
                    </button>
                )}
                <button
                    onClick={stopAndDo(() => onDelete(seq))}
                    title="Delete sequence"
                    className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/20 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
                >
                    <Trash2 size={12} />
                </button>
            </div>

            {/* Metrics strip — display only; the full breakdowns live on the detail page */}
            <div className="flex divide-x divide-border/40">
                {metrics.map((m) => (
                    <div key={m.label} className="flex-1 flex flex-col items-center justify-center px-3 py-3">
                        <p className={cn("text-sm font-semibold tabular-nums leading-none", m.color)}>{m.value.toLocaleString()}</p>
                        <p className="font-mono text-[9px] text-muted-foreground/40 tracking-widest uppercase mt-1">{m.label}</p>
                    </div>
                ))}
            </div>

            {/* High bounce rate warning — sender reputation guard */}
            {showBounceWarning && seq.status !== "draft" && (
                <div className="flex items-start gap-2 px-4 py-2 border-t border-amber-500/20 bg-amber-500/5 text-[11px] text-amber-300/90">
                    <AlertTriangle size={12} className="shrink-0 mt-0.5 text-amber-400" />
                    <span>
                        <span className="font-medium">High bounce rate ({Math.round(bounceRate * 100)}%)</span> — your contact list quality may be hurting domain reputation. Consider pausing and cleaning the list before sending more.
                    </span>
                </div>
            )}

            {/* Next-send summary */}
            {(seq.status === "active" || seq.status === "paused") && s.total > 0 && (
                <div className="flex items-center gap-2 px-4 py-2 border-t border-border/40 text-[11px]">
                    {seq.status === "paused" ? (
                        <span className="flex items-center gap-1.5 text-amber-500/70">
                            <Clock size={11} /> Paused — sending is on hold
                        </span>
                    ) : s.next_send_at ? (
                        <span className="flex items-center gap-1.5 text-foreground/70">
                            <Clock size={11} className="text-primary/60" />
                            Next send <span className="font-medium text-foreground/90">{fmtAbs(s.next_send_at)}</span>
                            <span className="text-muted-foreground/45">· {fmtRel(s.next_send_at)}</span>
                        </span>
                    ) : (
                        <span className="flex items-center gap-1.5 text-muted-foreground/50">
                            <Clock size={11} /> No more sends scheduled
                        </span>
                    )}
                    {s.replied > 0 && (
                        <span className="ml-auto font-mono text-teal-300/70 tabular-nums" title={`${s.replied} of ${s.total} replied`}>
                            {Math.round((s.replied / s.total) * 100)}% replied
                        </span>
                    )}
                </div>
            )}
        </Card>
    );
}
