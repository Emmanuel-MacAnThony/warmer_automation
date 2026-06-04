import {
    api,
    type Sequence,
    type SequenceBounce,
    type SequenceClick,
    type SequenceReply,
} from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { ConfirmDialog } from "@/shared/components/ui/dialog";
import { cn } from "@/shared/lib/utils";
import {
    AlertTriangle,
    ArrowLeft,
    Clock,
    Flame,
    Layers,
    Loader2,
    MessageSquare,
    MousePointerClick,
    Pause,
    Play,
    Trash2,
    XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "@/shared/lib/toast";
import { TIER_ROWS } from "../constants";
import { sentenceCase } from "../utils";
import { useOutreachContext } from "../context/OutreachContext";

// Reused formatters from SequenceCard.
function fmtAbs(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
        weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
    });
}
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

export function SequenceDetailView() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const seqId = id ? parseInt(id, 10) : NaN;
    const { toggleSequence, handleDeleteSequence, deleteSeqTarget, setDeleteSeqTarget, deletingSeq } = useOutreachContext();

    const [seq, setSeq] = useState<Sequence | null>(null);
    const [loading, setLoading] = useState(true);
    const [replies, setReplies] = useState<SequenceReply[] | null>(null);
    const [bounces, setBounces] = useState<SequenceBounce[] | null>(null);
    const [clicks, setClicks] = useState<SequenceClick[] | null>(null);

    // Initial + periodic refresh so live counts stay accurate while the user is parked here.
    const load = async () => {
        if (Number.isNaN(seqId)) return;
        try {
            const fresh = await api.getSequence(seqId);
            setSeq(fresh);
        } catch (e: any) {
            toast.error(e?.message ?? "Failed to load sequence");
        } finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        load();
        const t = setInterval(load, 8000);
        return () => clearInterval(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [seqId]);

    // Fetch the three engagement lists in parallel once the sequence is known.
    useEffect(() => {
        if (!seq) return;
        let cancelled = false;
        (async () => {
            const [r, b, c] = await Promise.all([
                api.getSequenceReplies(seq.id).catch(() => []),
                api.getSequenceBounces(seq.id).catch(() => []),
                api.getSequenceClicks(seq.id).catch(() => []),
            ]);
            if (cancelled) return;
            setReplies(r);
            setBounces(b);
            setClicks(c);
        })();
        return () => { cancelled = true; };
    }, [seq?.id]);

    if (Number.isNaN(seqId)) {
        return <NotFound onBack={() => navigate("/outreach")} />;
    }
    if (loading && !seq) {
        return (
            <div className="flex items-center justify-center py-24 text-[12px] text-muted-foreground gap-2">
                <Loader2 size={13} className="animate-spin" /> Loading sequence…
            </div>
        );
    }
    if (!seq) return <NotFound onBack={() => navigate("/outreach")} />;

    const tierCfg = TIER_ROWS.find((r) => r.key === seq.tier);
    const s = seq.stats ?? { total: 0, active: 0, replied: 0, completed: 0, stopped: 0, bounced: 0, by_step: {} };
    const stepCount = seq.steps?.length ?? Math.max(1, Object.keys(s.by_step).length);
    const clickedCount = s.unique_clickers ?? 0;
    const canToggle = seq.status === "active" || seq.status === "paused";

    // High-bounce warning, same threshold logic as the card.
    const reached = s.completed + s.replied + s.stopped + s.bounced + s.active;
    const bounceRate = reached >= 5 && s.bounced > 0 ? (s.bounced / reached) : 0;
    const showBounceWarning = bounceRate >= 0.05;

    // Project the per-step send schedule.
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

    const metrics = [
        { label: "Active",  value: s.active,   color: "text-primary" },
        { label: "Clicked", value: clickedCount, color: clickedCount > 0 ? "text-primary" : "text-muted-foreground/50" },
        { label: "Replied", value: s.replied,  color: s.replied > 0 ? "text-teal-300" : "text-muted-foreground/50" },
        { label: "Done",    value: s.completed, color: "text-muted-foreground/70" },
        { label: "Bounced", value: s.bounced,  color: s.bounced > 0 ? "text-red-500/75" : "text-muted-foreground/50" },
        { label: "Stopped", value: s.stopped,  color: s.stopped > 0 ? "text-amber-500/70" : "text-muted-foreground/50" },
    ];

    return (
        <div className="p-6 max-w-4xl mx-auto space-y-5">
            <button
                onClick={() => navigate("/outreach?tab=sequences")}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
                <ArrowLeft size={12} /> Back to sequences
            </button>

            {/* Header */}
            <div className="space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                    {tierCfg && (
                        <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-[11px] font-medium shrink-0", tierCfg.badge)}>
                            <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", tierCfg.dot)} />
                            {tierCfg.label}
                        </span>
                    )}
                    <span className="inline-flex items-center gap-1 text-[11px] font-mono text-muted-foreground/50">
                        <Layers size={11} /> {stepCount} step{stepCount !== 1 ? "s" : ""}
                    </span>
                    <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-wide", STATUS_STYLE[seq.status] ?? STATUS_STYLE.draft)}>
                        {seq.status}
                    </span>
                    <div className="ml-auto flex items-center gap-1">
                        {canToggle && (
                            <button
                                onClick={() => toggleSequence(seq)}
                                title={seq.status === "active" ? "Pause" : "Resume"}
                                className="h-7 w-7 rounded flex items-center justify-center text-muted-foreground/60 hover:text-foreground hover:bg-muted transition-colors"
                            >
                                {seq.status === "active" ? <Pause size={13} /> : <Play size={13} />}
                            </button>
                        )}
                        <button
                            onClick={() => setDeleteSeqTarget(seq)}
                            title="Delete sequence"
                            className="h-7 w-7 rounded flex items-center justify-center text-muted-foreground/30 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                            <Trash2 size={13} />
                        </button>
                    </div>
                </div>
                <h1 className="text-xl font-mono font-bold tracking-tight truncate">
                    {seq.campaign_goal ? sentenceCase(seq.campaign_goal) : seq.name}
                </h1>
                {(seq.status === "active" || seq.status === "paused") && s.next_send_at && (
                    <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                        <Clock size={12} className="text-primary/70" />
                        Next send <span className="font-medium text-foreground/85">{fmtAbs(s.next_send_at)}</span>
                        <span className="text-muted-foreground/50">· {fmtRel(s.next_send_at)}</span>
                    </p>
                )}
            </div>

            {/* High-bounce warning */}
            {showBounceWarning && seq.status !== "draft" && (
                <div className="flex items-start gap-2 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/5 text-[12px] text-amber-300/90">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5 text-amber-400" />
                    <span>
                        <span className="font-medium">High bounce rate ({Math.round(bounceRate * 100)}%)</span> — your contact list quality may be hurting domain reputation. Consider pausing and cleaning the list before sending more.
                    </span>
                </div>
            )}

            {/* Metrics strip */}
            <Card className="overflow-hidden">
                <div className="grid grid-cols-3 sm:grid-cols-6 divide-x divide-y sm:divide-y-0 divide-border/40">
                    {metrics.map((m) => (
                        <div key={m.label} className="flex flex-col items-center justify-center px-3 py-4">
                            <p className={cn("text-lg font-semibold tabular-nums leading-none", m.color)}>
                                {m.value.toLocaleString()}
                            </p>
                            <p className="font-mono text-[9px] text-muted-foreground/45 tracking-widest uppercase mt-1.5">
                                {m.label}
                            </p>
                        </div>
                    ))}
                </div>
            </Card>

            {/* Steps */}
            {ordered.length > 0 && (
                <Section icon={Layers} title="Steps">
                    <div className="space-y-1.5">
                        {ordered.map((st) => {
                            const waiting = s.by_step[String(st.step_number)] ?? 0;
                            const sched = schedule.get(st.step_number) ?? { label: "", tone: "idle" as const };
                            const tip = sched.tone === "scheduled" ? "Scheduled send time"
                                : sched.tone === "projected" ? `Projected — estimated as ${st.delay_days}d after the previous step's real send time`
                                : sched.tone === "sent" ? "Already sent (everyone advanced past this step)" : undefined;
                            return (
                                <div key={st.step_number} className="flex items-center gap-3 text-[12px]">
                                    <span className="h-5 w-5 rounded-full bg-muted/60 text-muted-foreground/70 text-[10px] font-mono flex items-center justify-center shrink-0">{st.step_number}</span>
                                    <span className="flex-1 min-w-0 truncate text-foreground/75" title={st.subject}>
                                        {st.step_number === 1 ? "" : "↳ "}{st.subject || "(no subject)"}
                                    </span>
                                    <span className={cn("text-[10px] font-mono shrink-0", SCHED_TONE[sched.tone])} title={tip}>{sched.label}</span>
                                    {waiting > 0 && (
                                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0" title="Contacts queued for this step — excludes anyone who replied or was stopped">
                                            {waiting} will send
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </Section>
            )}

            {/* Engagement sections — scrollable so long lists don't blow up the page */}
            <Section icon={MousePointerClick} title={`Clicked (${clickedCount})`} accent="primary" scrollable>
                <ContactList
                    items={clicks}
                    emptyText="No clicks recorded yet. Add a Pitch Page to your campaign to give every email a tracked CTA."
                    rowExtra={(c) => clickHotIndicator(c.click_count)}
                />
            </Section>

            <Section icon={MessageSquare} title={`Replied (${s.replied})`} accent="teal" scrollable>
                <ContactList items={replies} emptyText="No replies captured yet." />
            </Section>

            <Section icon={XCircle} title={`Bounced (${s.bounced})`} accent="red" scrollable>
                <ContactList
                    items={bounces}
                    emptyText="No bounces yet."
                    rowExtra={(b: SequenceBounce) => b.smtp_status ? (
                        <span className="font-mono text-[10px] text-red-400/70 shrink-0" title={b.reason ?? undefined}>
                            {b.smtp_status}{b.hard === false ? " (soft)" : ""}
                        </span>
                    ) : null}
                />
            </Section>

            <ConfirmDialog
                open={!!deleteSeqTarget}
                onOpenChange={(open) => { if (!open) setDeleteSeqTarget(null); }}
                title="Delete sequence?"
                description="This stops the sequence and removes it along with all its enrollment progress. Emails already sent are not recalled."
                confirmLabel="Delete"
                onConfirm={async () => {
                    await handleDeleteSequence();
                    navigate("/outreach?tab=sequences");
                }}
                loading={deletingSeq}
            />
        </div>
    );
}

/**
 * Hot-lead indicator for repeat clickers. Tiered:
 *   1 click   → nothing (just being in the list is the signal)
 *   2 clicks  → quiet ×N tag
 *   3+ clicks → flame + ×N — "this one's hot"
 *
 * The threshold matches the broader product cue: multiple clicks on the same
 * link strongly imply a real interested human, not a corporate link-scanner.
 */
function clickHotIndicator(count: number): React.ReactNode {
    if (count <= 1) return null;
    const isHot = count >= 3;
    return (
        <span
            className={cn(
                "inline-flex items-center gap-0.5 font-mono text-[10px] shrink-0",
                isHot ? "text-orange-400" : "text-primary/70",
            )}
            title={`Clicked ${count} times${isHot ? " — hot lead" : ""}`}
        >
            {isHot && <Flame size={10} className="shrink-0" />}
            ×{count}
        </span>
    );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function Section({ icon: Icon, title, accent, scrollable, children }: {
    icon: React.ComponentType<{ size?: number; className?: string }>;
    title: string;
    accent?: "primary" | "teal" | "red";
    /** Cap the body height with an inner scroll — for engagement lists that
     *  may grow unbounded (clicks, replies, bounces). */
    scrollable?: boolean;
    children: React.ReactNode;
}) {
    const accentClass =
        accent === "primary" ? "text-primary/80" :
        accent === "teal" ? "text-teal-300/80" :
        accent === "red" ? "text-red-400/80" :
        "text-muted-foreground/70";
    return (
        <Card className="overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/40">
                <Icon size={13} className={accentClass} />
                <h2 className="text-xs font-mono uppercase tracking-widest text-muted-foreground/70">{title}</h2>
            </div>
            <div className={cn("px-4 py-3", scrollable && "max-h-96 overflow-y-auto")}>{children}</div>
        </Card>
    );
}

// Shared row renderer for replies/bounces/clicks — they're all "contact + maybe extra info".
interface ContactRow { name: string; email: string; title: string; company: string }
function ContactList<T extends ContactRow>({
    items,
    emptyText,
    rowExtra,
}: {
    items: T[] | null;
    emptyText: string;
    rowExtra?: (item: T) => React.ReactNode;
}) {
    if (items === null) {
        return <div className="flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 size={11} className="animate-spin" /> Loading…</div>;
    }
    if (items.length === 0) {
        return <p className="text-[12px] text-muted-foreground/55 leading-relaxed">{emptyText}</p>;
    }
    return (
        <div className="space-y-1.5">
            {items.map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-[12px]">
                    <span className="text-foreground/85 truncate">{item.name}</span>
                    {rowExtra && rowExtra(item)}
                    {(item.title || item.company) && (
                        <span className="text-muted-foreground/40 truncate hidden sm:inline">
                            {[item.title, item.company].filter(Boolean).join(" · ")}
                        </span>
                    )}
                    {item.email && (
                        <span className="ml-auto font-mono text-muted-foreground/50 truncate shrink-0">{item.email}</span>
                    )}
                </div>
            ))}
        </div>
    );
}

function NotFound({ onBack }: { onBack: () => void }) {
    return (
        <div className="p-6 max-w-4xl mx-auto space-y-4">
            <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                <ArrowLeft size={12} /> Back
            </button>
            <Card className="py-16 px-8 text-center text-[13px] text-muted-foreground">
                Sequence not found.
            </Card>
        </div>
    );
}
