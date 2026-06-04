import { api, type Sequence, type SequenceBounce, type SequenceReply } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { AlertTriangle, ChevronRight, Clock, Layers, Loader2, Pause, Play, Trash2 } from "lucide-react";
import { useState } from "react";
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

export function SequenceCard({ seq, onToggle, onDelete }: { seq: Sequence; onToggle: (s: Sequence) => void; onDelete: (s: Sequence) => void }) {
    const tierCfg = TIER_ROWS.find((r) => r.key === seq.tier);
    const s = seq.stats ?? { total: 0, active: 0, replied: 0, completed: 0, stopped: 0, bounced: 0, by_step: {} };
    const stepCount = seq.steps?.length ?? Math.max(1, Object.keys(s.by_step).length);
    const canToggle = seq.status === "active" || seq.status === "paused";

    // Only one drawer expanded at a time. Mutually exclusive: opening one closes the other.
    const [expanded, setExpanded] = useState<"replies" | "bounces" | null>(null);
    const [replies, setReplies] = useState<SequenceReply[] | null>(null);
    const [loadingReplies, setLoadingReplies] = useState(false);
    const [bounces, setBounces] = useState<SequenceBounce[] | null>(null);
    const [loadingBounces, setLoadingBounces] = useState(false);

    const toggleReplies = async () => {
        const next = expanded === "replies" ? null : "replies";
        setExpanded(next);
        if (next === "replies" && replies === null) {
            setLoadingReplies(true);
            try { setReplies(await api.getSequenceReplies(seq.id)); }
            catch { setReplies([]); }
            finally { setLoadingReplies(false); }
        }
    };

    const toggleBounces = async () => {
        const next = expanded === "bounces" ? null : "bounces";
        setExpanded(next);
        if (next === "bounces" && bounces === null) {
            setLoadingBounces(true);
            try { setBounces(await api.getSequenceBounces(seq.id)); }
            catch { setBounces([]); }
            finally { setLoadingBounces(false); }
        }
    };

    const metrics = [
        { label: "Active",  value: s.active,    color: "text-primary",
          hint: "Contacts still in the pipeline — includes those waiting between steps (e.g. between send 1 and the 3-day follow-up)." },
        { label: "Replied", value: s.replied,   color: s.replied > 0 ? "text-teal-300" : "text-muted-foreground/50",
          hint: "Replied — sequence stopped for them." },
        { label: "Done",    value: s.completed, color: "text-muted-foreground/70",
          hint: "Reached the final step." },
        { label: "Bounced", value: s.bounced,   color: s.bounced > 0 ? "text-red-500/75" : "text-muted-foreground/50",
          hint: "Address rejected (MX fail, Gmail sync error, or DSN bounce) — contact added to the suppression list." },
        { label: "Stopped", value: s.stopped,   color: s.stopped > 0 ? "text-amber-500/70" : "text-muted-foreground/50",
          hint: "Stopped (no deliverable address, template missing, or other terminal error)." },
    ];

    // High-bounce-rate warning. Once 5+ contacts have been actually sent to, if
    // ≥5% of them bounce, warn the fundraiser so they can pause + clean the list
    // before sender reputation suffers further.
    const reached = s.completed + s.replied + s.stopped + s.bounced + s.active;
    const bounceRate = reached >= 5 && s.bounced > 0 ? (s.bounced / reached) : 0;
    const showBounceWarning = bounceRate >= 0.05;

    // Per-step schedule. Anchor on the first step that has a REAL next_send_at
    // (contacts actually queued there). Steps AFTER the anchor are projected
    // forward using each step's delay_days; steps BEFORE it are 'sent' (everyone
    // advanced past them). When no real anchor exists, fall back to the relative
    // cadence text — we never fake a clock time from now().
    const DAY = 86_400_000;
    const ordered = [...(seq.step_previews ?? [])].sort((a, b) => a.step_number - b.step_number);
    type Sched = { label: string; tone: "scheduled" | "projected" | "sent" | "idle" };
    const schedule = new Map<number, Sched>();
    let firstAnchorStep: number | null = null;
    let prevT: number | null = null;
    for (const st of ordered) {
        const real = s.next_by_step?.[String(st.step_number)];
        if (real) {
            if (firstAnchorStep === null) firstAnchorStep = st.step_number;
            prevT = new Date(real).getTime();
            schedule.set(st.step_number, { label: fmtAbs(real), tone: "scheduled" });
        } else if (prevT !== null) {
            const t: number = prevT + st.delay_days * DAY;
            prevT = t;
            schedule.set(st.step_number, { label: "~" + fmtAbs(new Date(t).toISOString()), tone: "projected" });
        } else {
            schedule.set(st.step_number, {
                label: st.step_number === 1 ? "sends first" : `+${st.delay_days}d after prev`,
                tone: "idle",
            });
        }
    }
    if (firstAnchorStep !== null) {
        for (const st of ordered) {
            if (st.step_number < firstAnchorStep) {
                schedule.set(st.step_number, { label: "sent", tone: "sent" });
            }
        }
    }
    const SCHED_TONE: Record<Sched["tone"], string> = {
        scheduled: "text-foreground/60",
        projected: "text-muted-foreground/45",
        sent:      "text-muted-foreground/35",
        idle:      "text-muted-foreground/35 italic",
    };

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
                    const isReplied = m.label === "Replied" && s.replied > 0;
                    const isBounced = m.label === "Bounced" && s.bounced > 0;
                    const clickable = isReplied || isBounced;
                    const onClick = isReplied ? toggleReplies : isBounced ? toggleBounces : undefined;
                    const isOpen = (isReplied && expanded === "replies") || (isBounced && expanded === "bounces");
                    return (
                        <button
                            key={m.label}
                            onClick={onClick}
                            disabled={!clickable}
                            className={cn(
                                "flex-1 flex flex-col items-center justify-center px-3 py-3 transition-colors",
                                clickable && isReplied ? "hover:bg-teal-300/5 cursor-pointer" :
                                clickable && isBounced ? "hover:bg-red-500/5 cursor-pointer" :
                                "cursor-default",
                            )}
                            title={
                                isReplied ? "View who replied" :
                                isBounced ? "View who bounced" :
                                m.hint
                            }
                        >
                            <p className={cn("text-sm font-semibold tabular-nums leading-none", m.color)}>{m.value.toLocaleString()}</p>
                            <p className="font-mono text-[9px] text-muted-foreground/40 tracking-widest uppercase mt-1 flex items-center gap-0.5">
                                {m.label}
                                {clickable && <ChevronRight size={9} className={cn("transition-transform", isOpen && "rotate-90")} />}
                            </p>
                        </button>
                    );
                })}
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

            {/* Next-send summary — when the next batch goes out + reply rate */}
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

            {/* Hot leads — who replied */}
            {expanded === "replies" && (
                <div className="border-t border-teal-300/15 bg-teal-300/5 px-4 py-2.5">
                    {loadingReplies ? (
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 size={11} className="animate-spin" /> Loading replies…</div>
                    ) : !replies || replies.length === 0 ? (
                        <p className="text-[11px] text-muted-foreground/50">No replies captured yet.</p>
                    ) : (
                        <div className="space-y-1.5">
                            <p className="text-[9px] font-mono uppercase tracking-widest text-teal-300/60">Replied — follow up personally</p>
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
            {/* Bounces — who couldn't be reached */}
            {expanded === "bounces" && (
                <div className="border-t border-red-500/15 bg-red-500/5 px-4 py-2.5">
                    {loadingBounces ? (
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 size={11} className="animate-spin" /> Loading bounces…</div>
                    ) : !bounces || bounces.length === 0 ? (
                        <p className="text-[11px] text-muted-foreground/50">No bounces yet.</p>
                    ) : (
                        <div className="space-y-1.5">
                            <p className="text-[9px] font-mono uppercase tracking-widest text-red-400/70">Bounced — suppressed from future campaigns</p>
                            {bounces.map((b, i) => (
                                <div key={i} className="flex items-center gap-2 text-[11px]">
                                    <span className="text-foreground/80 truncate">{b.name}</span>
                                    {b.smtp_status && (
                                        <span className="font-mono text-[9px] text-red-400/70 shrink-0" title={b.reason ?? undefined}>
                                            {b.smtp_status}{b.hard === false ? " (soft)" : ""}
                                        </span>
                                    )}
                                    {(b.title || b.company) && (
                                        <span className="text-muted-foreground/40 truncate hidden sm:inline">{[b.title, b.company].filter(Boolean).join(" · ")}</span>
                                    )}
                                    {b.email && <span className="ml-auto font-mono text-muted-foreground/50 truncate shrink-0">{b.email}</span>}
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
                    {ordered.map((st) => {
                        const waiting = s.by_step[String(st.step_number)] ?? 0;
                        const sched = schedule.get(st.step_number) ?? { label: "", tone: "idle" as const };
                        const tip = sched.tone === "scheduled" ? "Scheduled send time"
                            : sched.tone === "projected" ? `Projected — estimated as ${st.delay_days}d after the previous step's real send time`
                            : sched.tone === "sent" ? "Already sent (everyone advanced past this step)"
                            : undefined;
                        return (
                            <div key={st.step_number} className="flex items-center gap-2 text-[11px]">
                                <span className="h-4 w-4 rounded-full bg-muted/60 text-muted-foreground/70 text-[9px] font-mono flex items-center justify-center shrink-0">{st.step_number}</span>
                                <span className="flex-1 min-w-0 truncate text-foreground/70" title={st.subject}>
                                    {st.step_number === 1 ? "" : "↳ "}{st.subject || "(no subject)"}
                                </span>
                                <span className={cn("text-[9px] font-mono shrink-0", SCHED_TONE[sched.tone])} title={tip}>{sched.label}</span>
                                {waiting > 0 && (
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0" title="Contacts queued for this step — excludes anyone who replied or was stopped">
                                        {waiting} will send
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
