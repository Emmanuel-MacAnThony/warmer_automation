import { api, type Sequence, type SequenceReply } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { ChevronRight, Layers, Loader2, Pause, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { TIER_ROWS } from "../constants";
import { sentenceCase } from "../utils";

const STATUS_STYLE: Record<string, string> = {
    active:    "text-emerald-400 bg-emerald-500/10 border-emerald-500/25",
    paused:    "text-amber-400 bg-amber-500/10 border-amber-500/25",
    draft:     "text-muted-foreground bg-muted/40 border-border/40",
    completed: "text-blue-400 bg-blue-500/10 border-blue-500/25",
};

export function SequenceCard({ seq, onToggle, onDelete }: { seq: Sequence; onToggle: (s: Sequence) => void; onDelete: (s: Sequence) => void }) {
    const tierCfg = TIER_ROWS.find((r) => r.key === seq.tier);
    const s = seq.stats ?? { total: 0, active: 0, replied: 0, completed: 0, stopped: 0, bounced: 0, by_step: {} };
    const stepCount = seq.steps?.length ?? Math.max(1, Object.keys(s.by_step).length);
    const canToggle = seq.status === "active" || seq.status === "paused";

    const [showReplies, setShowReplies] = useState(false);
    const [replies, setReplies] = useState<SequenceReply[] | null>(null);
    const [loadingReplies, setLoadingReplies] = useState(false);

    const toggleReplies = async () => {
        const next = !showReplies;
        setShowReplies(next);
        if (next && replies === null) {
            setLoadingReplies(true);
            try { setReplies(await api.getSequenceReplies(seq.id)); }
            catch { setReplies([]); }
            finally { setLoadingReplies(false); }
        }
    };

    const metrics = [
        { label: "Active",  value: s.active,    color: "text-primary" },
        { label: "Replied", value: s.replied,   color: s.replied > 0 ? "text-emerald-500" : "text-muted-foreground/50" },
        { label: "Done",    value: s.completed, color: "text-muted-foreground/70" },
        { label: "Stopped", value: s.stopped,   color: s.stopped > 0 ? "text-amber-500/70" : "text-muted-foreground/50" },
    ];

    return (
        <Card className="overflow-hidden w-full">
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
                        onClick={() => onToggle(seq)}
                        title={seq.status === "active" ? "Pause" : "Resume"}
                        className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/50 hover:text-foreground hover:bg-muted transition-colors shrink-0"
                    >
                        {seq.status === "active" ? <Pause size={12} /> : <Play size={12} />}
                    </button>
                )}
                <button
                    onClick={() => onDelete(seq)}
                    title="Delete sequence"
                    className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/20 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
                >
                    <Trash2 size={12} />
                </button>
            </div>
            <div className="flex divide-x divide-border/40">
                {metrics.map((m) => {
                    const clickable = m.label === "Replied" && s.replied > 0;
                    return (
                        <button
                            key={m.label}
                            onClick={clickable ? toggleReplies : undefined}
                            disabled={!clickable}
                            className={cn(
                                "flex-1 flex flex-col items-center justify-center px-3 py-3 transition-colors",
                                clickable ? "hover:bg-emerald-500/5 cursor-pointer" : "cursor-default",
                            )}
                            title={clickable ? "View who replied" : undefined}
                        >
                            <p className={cn("text-sm font-semibold tabular-nums leading-none", m.color)}>{m.value.toLocaleString()}</p>
                            <p className="font-mono text-[9px] text-muted-foreground/40 tracking-widest uppercase mt-1 flex items-center gap-0.5">
                                {m.label}
                                {clickable && <ChevronRight size={9} className={cn("transition-transform", showReplies && "rotate-90")} />}
                            </p>
                        </button>
                    );
                })}
            </div>

            {/* Hot leads — who replied */}
            {showReplies && (
                <div className="border-t border-emerald-500/15 bg-emerald-500/5 px-4 py-2.5">
                    {loadingReplies ? (
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 size={11} className="animate-spin" /> Loading replies…</div>
                    ) : !replies || replies.length === 0 ? (
                        <p className="text-[11px] text-muted-foreground/50">No replies captured yet.</p>
                    ) : (
                        <div className="space-y-1.5">
                            <p className="text-[9px] font-mono uppercase tracking-widest text-emerald-400/60">Replied — follow up personally</p>
                            {replies.map((r, i) => (
                                <div key={i} className="flex items-center gap-2 text-[11px]">
                                    <span className="text-foreground/80 truncate">{r.name}</span>
                                    {(r.title || r.company) && (
                                        <span className="text-muted-foreground/40 truncate hidden sm:inline">{[r.title, r.company].filter(Boolean).join(" · ")}</span>
                                    )}
                                    {r.email && <span className="ml-auto font-mono text-muted-foreground/50 truncate shrink-0">{r.email}</span>}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
            {/* Steps — what each touch is + how many contacts are waiting on it */}
            {(seq.step_previews?.length ?? 0) > 0 && (
                <div className="px-4 py-2.5 border-t border-border/40 space-y-1.5">
                    <span className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40">Steps</span>
                    {seq.step_previews!.map((st) => {
                        const waiting = s.by_step[String(st.step_number)] ?? 0;
                        const when = st.step_number === 1 ? "sends first" : `+${st.delay_days}d after prev`;
                        return (
                            <div key={st.step_number} className="flex items-center gap-2 text-[11px]">
                                <span className="h-4 w-4 rounded-full bg-muted/60 text-muted-foreground/70 text-[9px] font-mono flex items-center justify-center shrink-0">{st.step_number}</span>
                                <span className="flex-1 min-w-0 truncate text-foreground/70" title={st.subject}>
                                    {st.step_number === 1 ? "" : "↳ "}{st.subject || "(no subject)"}
                                </span>
                                <span className="text-[9px] font-mono text-muted-foreground/40 shrink-0">{when}</span>
                                {waiting > 0 && (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0" title="contacts waiting on this step">
                                        {waiting} waiting
                                    </span>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </Card>
    );
}
