import { api, type BatchJobBounce, type BatchJobDetail, type CampaignTemplate, type SequenceClick } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@/shared/components/ui/sheet";
import { cn } from "@/shared/lib/utils";
import { motion } from "framer-motion";
import {
    AlertTriangle,
    ArrowLeft,
    FileText,
    Flame,
    Link2,
    Loader2,
    MousePointerClick,
    XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "@/shared/lib/toast";
import { EMAIL_JOB_STATUS, TIER_META } from "@/features/jobs/utils";

function fmtAbs(iso?: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(undefined, {
        weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
    });
}

export function BatchJobDetailView() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const jobId = id ? parseInt(id, 10) : NaN;

    const [job, setJob] = useState<BatchJobDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [bounces, setBounces] = useState<BatchJobBounce[] | null>(null);
    const [clicks, setClicks] = useState<SequenceClick[] | null>(null);
    // Slide-in template drawer — fetched on first open, cached afterwards.
    const [templateOpen, setTemplateOpen] = useState(false);
    const [template, setTemplate] = useState<CampaignTemplate | null>(null);
    const [loadingTemplate, setLoadingTemplate] = useState(false);

    const load = async () => {
        if (Number.isNaN(jobId)) return;
        try {
            const fresh = await api.getBatchJob(jobId);
            setJob(fresh);
        } catch (e: any) {
            toast.error(e?.message ?? "Failed to load batch job");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
        const t = setInterval(load, 5000);
        return () => clearInterval(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [jobId]);

    useEffect(() => {
        if (!job) return;
        let cancelled = false;
        (async () => {
            const [b, c] = await Promise.all([
                api.getBatchJobBounces(job.id).catch(() => []),
                api.getBatchJobClicks(job.id).catch(() => []),
            ]);
            if (cancelled) return;
            setBounces(b);
            setClicks(c);
        })();
        return () => { cancelled = true; };
    }, [job?.id]);

    const openTemplate = async () => {
        setTemplateOpen(true);
        if (template !== null || !job) return;
        setLoadingTemplate(true);
        try {
            const t = await api.getTemplateById(job.campaign_id, job.template_id);
            setTemplate(t);
        } catch (e: any) {
            toast.error(e?.message ?? "Failed to load template");
        } finally {
            setLoadingTemplate(false);
        }
    };

    if (Number.isNaN(jobId)) return <NotFound onBack={() => navigate("/outreach?tab=jobs")} />;
    if (loading && !job) {
        return (
            <div className="flex items-center justify-center py-24 text-[12px] text-muted-foreground gap-2">
                <Loader2 size={13} className="animate-spin" /> Loading batch job…
            </div>
        );
    }
    if (!job) return <NotFound onBack={() => navigate("/outreach?tab=jobs")} />;

    const tier      = TIER_META[job.tier]          ?? TIER_META.tier_1;
    const status    = EMAIL_JOB_STATUS[job.status] ?? EMAIL_JOB_STATUS.pending;
    const remaining = Math.max(0, job.total - job.sent - job.failed);
    const pct       = job.total > 0 ? Math.min(100, Math.round((job.sent / job.total) * 100)) : 0;
    const bouncedCount = bounces?.length ?? 0;
    const clickedCount = clicks?.length ?? 0;

    // High-bounce warning, parallel to the sequence card: 5% over a 5-contact floor.
    const bounceRate = job.sent >= 5 && bouncedCount > 0 ? (bouncedCount / job.sent) : 0;
    const showBounceWarning = bounceRate >= 0.05;

    const metrics = [
        { label: "Total",     value: job.total,    color: "text-foreground/75" },
        { label: "Sent",      value: job.sent,     color: "text-primary/85" },
        { label: "Clicked",   value: clickedCount, color: clickedCount > 0 ? "text-primary" : "text-muted-foreground/50" },
        { label: "Failed",    value: job.failed,   color: job.failed > 0 ? "text-amber-500/80" : "text-muted-foreground/50" },
        { label: "Bounced",   value: bouncedCount, color: bouncedCount > 0 ? "text-red-500/75" : "text-muted-foreground/50" },
        { label: "Remaining", value: remaining,    color: "text-muted-foreground/60" },
    ];

    return (
        <div className="p-6 max-w-4xl mx-auto space-y-5">
            <button
                onClick={() => navigate("/outreach?tab=jobs")}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
                <ArrowLeft size={12} /> Back to jobs
            </button>

            {/* Header */}
            <div className="space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-[11px] font-medium shrink-0", tier.badge)}>
                        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", tier.dot)} />
                        {tier.label}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono ml-auto">
                        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", status.dot)} />
                        <span className={cn(status.text)}>{status.label}</span>
                    </span>
                </div>
                <h1 className="text-xl font-mono font-bold tracking-tight truncate">
                    {job.campaign_goal}
                </h1>
                <div className="flex items-center gap-4 text-[11px] font-mono text-muted-foreground/55 flex-wrap">
                    <span>Created {fmtAbs(job.created_at)}</span>
                    {job.started_at && <span>Started {fmtAbs(job.started_at)}</span>}
                    {job.completed_at && <span>Completed {fmtAbs(job.completed_at)}</span>}
                </div>
            </div>

            {/* Progress bar */}
            <Card className="overflow-hidden">
                <div className="px-4 py-4 space-y-2.5">
                    <div className="flex items-baseline gap-3 text-sm">
                        <span className="font-semibold tabular-nums text-foreground">
                            {job.sent.toLocaleString()}
                            {job.total > 0 && (
                                <span className="text-muted-foreground/70">/{job.total.toLocaleString()} ({pct}%)</span>
                            )}
                        </span>
                        <span className="text-muted-foreground/60 text-[11px] font-mono uppercase tracking-widest">sent</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted/30 overflow-hidden">
                        <motion.div
                            className="h-full bg-primary/70 rounded-full"
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.6, ease: "easeOut" }}
                        />
                    </div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-6 divide-x divide-y sm:divide-y-0 divide-border/40 border-t border-border/40">
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

            {/* Retry banner */}
            {job.retry_after && (
                <div className="flex items-start gap-2 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/5 text-[12px] text-amber-300/90">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5 text-amber-400" />
                    <span>Rate limited — will resume after <span className="font-medium">{fmtAbs(job.retry_after)}</span>.</span>
                </div>
            )}

            {/* High bounce rate warning */}
            {showBounceWarning && (
                <div className="flex items-start gap-2 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/5 text-[12px] text-amber-300/90">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5 text-amber-400" />
                    <span>
                        <span className="font-medium">High bounce rate ({Math.round(bounceRate * 100)}%)</span> — domain reputation may be affected. Consider cleaning the list before more sends.
                    </span>
                </div>
            )}

            {/* Error banner */}
            {job.error && (
                <div className="flex items-start gap-2 px-4 py-2.5 rounded-lg border border-red-500/20 bg-red-500/5 text-[12px] text-red-300/90">
                    <XCircle size={13} className="shrink-0 mt-0.5 text-red-400" />
                    <span>{job.error}</span>
                </div>
            )}

            {/* Pitch page (if set on the campaign) */}
            {job.pitch_page_url && (
                <Section icon={Link2} title="Pitch page (tracked CTA on every email)">
                    <a
                        href={job.pitch_page_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-[12px] font-mono text-primary/85 hover:text-primary truncate"
                    >
                        {job.pitch_page_label || "Learn more"} → <span className="text-primary/55 truncate">{job.pitch_page_url}</span>
                    </a>
                </Section>
            )}

            {/* Template — slides in from the right instead of navigating away */}
            <Section icon={FileText} title="Template">
                <button
                    onClick={openTemplate}
                    className="inline-flex items-center gap-1.5 text-[12px] font-mono text-muted-foreground hover:text-primary transition-colors"
                >
                    Template #{job.template_id} →
                </button>
            </Section>

            {/* Clicked — strongest engagement signal */}
            <Section icon={MousePointerClick} title={`Clicked (${clickedCount})`} accent="primary" scrollable>
                {clicks === null ? (
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 size={11} className="animate-spin" /> Loading…</div>
                ) : clicks.length === 0 ? (
                    <p className="text-[12px] text-muted-foreground/55 leading-relaxed">
                        No clicks recorded yet. Add a Pitch Page to your campaign to give every email a tracked CTA.
                    </p>
                ) : (
                    <div className="space-y-1.5">
                        {clicks.map((c, i) => (
                            <div key={i} className="flex items-center gap-2 text-[12px]">
                                <span className="text-foreground/85 truncate">{c.name}</span>
                                {clickHotIndicator(c.click_count)}
                                {(c.title || c.company) && (
                                    <span className="text-muted-foreground/40 truncate hidden sm:inline">{[c.title, c.company].filter(Boolean).join(" · ")}</span>
                                )}
                                {c.email && (
                                    <span className="ml-auto font-mono text-muted-foreground/50 truncate shrink-0">{c.email}</span>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </Section>

            {/* Bounced */}
            <Section icon={XCircle} title={`Bounced (${bouncedCount})`} accent="red" scrollable>
                {bounces === null ? (
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 size={11} className="animate-spin" /> Loading…</div>
                ) : bounces.length === 0 ? (
                    <p className="text-[12px] text-muted-foreground/55 leading-relaxed">No bounces from this job.</p>
                ) : (
                    <div className="space-y-1.5">
                        {bounces.map((b, i) => (
                            <div key={i} className="flex items-center gap-2 text-[12px]">
                                <span className="text-foreground/85 truncate">{b.name}</span>
                                {b.smtp_status && (
                                    <span className="font-mono text-[10px] text-red-400/70 shrink-0" title={b.reason ?? undefined}>
                                        {b.smtp_status}{b.hard === false ? " (soft)" : ""}
                                    </span>
                                )}
                                {(b.title || b.company) && (
                                    <span className="text-muted-foreground/40 truncate hidden sm:inline">
                                        {[b.title, b.company].filter(Boolean).join(" · ")}
                                    </span>
                                )}
                                {b.email && (
                                    <span className="ml-auto font-mono text-muted-foreground/50 truncate shrink-0">{b.email}</span>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </Section>

            {/* Template slide-in drawer */}
            <Sheet open={templateOpen} onOpenChange={setTemplateOpen}>
                <SheetContent side="right" className="w-full sm:max-w-xl flex flex-col">
                    <SheetHeader>
                        <SheetTitle className="font-mono">Template #{job.template_id}</SheetTitle>
                        <SheetDescription>
                            {tier.label} · campaign {job.campaign_id}
                        </SheetDescription>
                    </SheetHeader>
                    <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-5">
                        {loadingTemplate ? (
                            <div className="flex items-center gap-2 text-[12px] text-muted-foreground py-12 justify-center">
                                <Loader2 size={13} className="animate-spin" /> Loading template…
                            </div>
                        ) : !template ? (
                            <p className="text-[12px] text-muted-foreground/55 py-8 text-center">
                                Template not found.
                            </p>
                        ) : (
                            <>
                                <div className="space-y-1">
                                    <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/45">Subject</p>
                                    <p className="text-[13px] font-medium text-foreground/90">{template.subject || "(no subject)"}</p>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/45">Body</p>
                                    <div
                                        className="text-[13px] leading-relaxed text-foreground/80 whitespace-pre-wrap font-sans break-words"
                                        dangerouslySetInnerHTML={{ __html: template.body || "<em class='text-muted-foreground/40'>(empty)</em>" }}
                                    />
                                </div>
                                {job.pitch_page_url && (
                                    <div className="space-y-1 pt-3 border-t border-border/40">
                                        <p className="text-[9px] font-mono uppercase tracking-widest text-primary/60">Auto-appended CTA</p>
                                        <p className="text-[12px] text-muted-foreground/75">
                                            Every send for this campaign gets a tracked button added at the end of the body:
                                        </p>
                                        <p className="text-[12px] font-mono">
                                            <span className="text-foreground/85">{job.pitch_page_label || "Learn more"}</span>
                                            <span className="text-muted-foreground/55"> → {job.pitch_page_url}</span>
                                        </p>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </SheetContent>
            </Sheet>
        </div>
    );
}

/**
 * Hot-lead indicator for repeat clickers — mirrors the sequence detail view:
 *   1 click   → nothing (already in the list)
 *   2 clicks  → quiet ×N tag
 *   3+ clicks → flame + ×N — "this one's hot"
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
    /** Cap the body height with an inner scroll — used for engagement lists. */
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

function NotFound({ onBack }: { onBack: () => void }) {
    return (
        <div className="p-6 max-w-4xl mx-auto space-y-4">
            <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                <ArrowLeft size={12} /> Back
            </button>
            <Card className="py-16 px-8 text-center text-[13px] text-muted-foreground">
                Batch job not found.
            </Card>
        </div>
    );
}
