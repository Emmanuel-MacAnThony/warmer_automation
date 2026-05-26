import { cn } from "@/shared/lib/utils";
import { motion } from "framer-motion";
import { AlertTriangle, Pause, PenLine, Play, X } from "lucide-react";
import { useBatchEditor } from "../../context/batch/BatchEditorContext";
import { useBatchSend } from "../../context/batch/BatchSendContext";

export function DetailsStep() {
    const { template } = useBatchEditor();
    const {
        activeJob, currentContact,
        pauseReason, setPauseReason,
        confirmCancelJob, setConfirmCancelJob,
        handlePauseJob, handleResumeJob, handleCancelActiveJob,
        setShowTplDrawer, setDrawerTemplate,
    } = useBatchSend();

    const handleShowTemplate = () => {
        if (template) setDrawerTemplate(template);
        setShowTplDrawer(true);
    };

    return (
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
            {pauseReason && (
                <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/8 px-4 py-3">
                    <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="flex-1 text-[12px] font-mono text-amber-300/80 leading-relaxed">{pauseReason}</p>
                    <button
                        onClick={() => setPauseReason(null)}
                        className="text-amber-400/40 hover:text-amber-400 transition-colors shrink-0"
                    >
                        <X size={13} />
                    </button>
                </div>
            )}
            {activeJob ? (
                <div
                    className={cn(
                        "rounded-xl border overflow-hidden",
                        activeJob.status === "running"   ? "border-primary/20 bg-primary/5"
                        : activeJob.status === "completed"  ? "border-emerald-500/20 bg-emerald-500/5"
                        : activeJob.status === "failed"     ? "border-red-500/20 bg-red-500/5"
                        : activeJob.status === "cancelled"  ? "border-border/40 bg-muted/10"
                        : /* pending | paused */               "border-amber-500/20 bg-amber-500/5",
                    )}
                >
                    <div className="flex items-center gap-3 px-4 py-3 border-b border-inherit">
                        <div
                            className={cn(
                                "h-2 w-2 rounded-full shrink-0",
                                activeJob.status === "running"   ? "bg-primary/70 animate-pulse"
                                : activeJob.status === "completed"  ? "bg-emerald-500"
                                : activeJob.status === "failed"     ? "bg-red-500"
                                : activeJob.status === "cancelled"  ? "bg-muted-foreground/30"
                                : activeJob.status === "paused"     ? "bg-amber-400"
                                : /* pending */                       "bg-amber-400 animate-pulse",
                            )}
                        />
                        <span
                            className={cn(
                                "text-[11px] font-mono font-semibold uppercase tracking-widest",
                                activeJob.status === "running"   ? "text-primary/80"
                                : activeJob.status === "completed"  ? "text-emerald-500/80"
                                : activeJob.status === "failed"     ? "text-red-400"
                                : activeJob.status === "cancelled"  ? "text-muted-foreground/40"
                                : activeJob.status === "paused"     ? "text-amber-400"
                                : /* pending */                       "text-amber-500/80",
                            )}
                        >
                            {activeJob.status === "running"   ? "Sending"
                            : activeJob.status === "completed"  ? "Completed"
                            : activeJob.status === "failed"     ? "Failed"
                            : activeJob.status === "cancelled"  ? "Cancelled"
                            : activeJob.status === "paused"     ? "Paused"
                            : /* pending */                       "Queued"}
                        </span>
                        <span className="text-muted-foreground/30 text-[11px]">·</span>
                        <span className="text-[11px] text-muted-foreground/50 font-mono tabular-nums">
                            {activeJob.total.toLocaleString()} recipients
                        </span>

                        {/* Job controls */}
                        <div className="ml-auto flex items-center gap-1.5">
                            {activeJob.status === "running" && (
                                <button
                                    onClick={handlePauseJob}
                                    title="Pause job"
                                    className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/40 hover:text-amber-400 hover:bg-amber-500/10 transition-colors"
                                >
                                    <Pause size={11} />
                                </button>
                            )}
                            {activeJob.status === "paused" && (
                                <button
                                    onClick={handleResumeJob}
                                    title="Resume job"
                                    className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/40 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                                >
                                    <Play size={11} />
                                </button>
                            )}
                            {(activeJob.status === "running" || activeJob.status === "paused" || activeJob.status === "pending") && (
                                confirmCancelJob ? (
                                    <div className="flex items-center gap-1">
                                        <span className="text-[10px] text-muted-foreground/50 font-mono">Cancel?</span>
                                        <button
                                            onClick={handleCancelActiveJob}
                                            className="px-1.5 py-0.5 rounded text-[10px] font-medium text-red-400 hover:bg-red-500/10 transition-colors"
                                        >
                                            Yes
                                        </button>
                                        <button
                                            onClick={() => setConfirmCancelJob(false)}
                                            className="px-1.5 py-0.5 rounded text-[10px] font-medium text-muted-foreground/40 hover:bg-muted transition-colors"
                                        >
                                            No
                                        </button>
                                    </div>
                                ) : (
                                    <button
                                        onClick={() => setConfirmCancelJob(true)}
                                        title="Cancel job"
                                        className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/30 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                    >
                                        <X size={11} />
                                    </button>
                                )
                            )}
                            <span className="text-[10px] text-muted-foreground/40 font-mono pl-1">
                                {new Date(activeJob.created_at).toLocaleDateString("en-US", {
                                    month: "short", day: "numeric", year: "numeric",
                                })}
                            </span>
                        </div>
                    </div>

                    {activeJob.total > 0 && (
                        <div className="px-4 pt-3 pb-2 space-y-2">
                            <div className="flex items-center justify-between">
                                <span className="text-xs text-muted-foreground/40">
                                    Progress
                                </span>
                                <span className="text-[10px] font-mono tabular-nums text-muted-foreground/50">
                                    {Math.round((activeJob.sent / activeJob.total) * 100)}%
                                </span>
                            </div>
                            <div className="h-1.5 bg-muted/40 rounded-full overflow-hidden">
                                <motion.div
                                    className="h-full rounded-full bg-primary/70"
                                    initial={false}
                                    animate={{ width: `${Math.round((activeJob.sent / activeJob.total) * 100)}%` }}
                                    transition={{ duration: 0.5, ease: "easeOut" }}
                                />
                            </div>
                            {/* Live ticker — shown while running */}
                            {activeJob.status === "running" && (
                                <div className="flex items-center gap-1.5 min-h-4">
                                    <span className="w-1 h-1 rounded-full bg-primary/60 animate-pulse shrink-0" />
                                    <span className="text-[10px] font-mono text-muted-foreground/40 truncate">
                                        {currentContact ? `→ ${currentContact}` : "Starting…"}
                                    </span>
                                </div>
                            )}
                            {activeJob.status === "paused" && activeJob.sent > 0 && (
                                <p className="text-[10px] font-mono text-amber-400/60">
                                    Paused after {activeJob.sent.toLocaleString()} sent — resume to continue
                                </p>
                            )}
                        </div>
                    )}

                    <div className="grid grid-cols-4 border-t border-inherit divide-x divide-border/20">
                        {[
                            { label: "Total", value: activeJob.total, color: "text-foreground/60" },
                            { label: "Sent", value: activeJob.sent, color: activeJob.sent > 0 ? "text-primary/70" : "text-muted-foreground/35" },
                            { label: "Failed", value: activeJob.failed, color: activeJob.failed > 0 ? "text-red-400" : "text-muted-foreground/35" },
                            { label: "Remaining", value: Math.max(0, activeJob.total - activeJob.sent - activeJob.failed), color: "text-muted-foreground/55" },
                        ].map((s) => (
                            <div key={s.label} className="flex flex-col items-center py-4 gap-1.5">
                                <span className={cn("text-2xl font-bold tabular-nums leading-none tracking-tight", s.color)}>
                                    {s.value.toLocaleString()}
                                </span>
                                <span className="text-xs text-muted-foreground/40">
                                    {s.label}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            ) : (
                <div className="rounded-xl border border-border/40 overflow-hidden animate-pulse">
                    <div className="flex items-center gap-3 px-4 py-3 border-b border-border/30">
                        <div className="h-2 w-2 rounded-full bg-muted-foreground/15 shrink-0" />
                        <div className="h-2.5 w-14 rounded bg-muted-foreground/12" />
                        <div className="h-2 w-1 rounded bg-muted-foreground/10" />
                        <div className="h-2.5 w-20 rounded bg-muted-foreground/10" />
                        <div className="ml-auto h-2 w-16 rounded bg-muted-foreground/10" />
                    </div>
                    <div className="px-4 pt-3 pb-2 space-y-2.5">
                        <div className="flex justify-between">
                            <div className="h-2 w-10 rounded bg-muted-foreground/10" />
                            <div className="h-2 w-6 rounded bg-muted-foreground/10" />
                        </div>
                        <div className="h-1.5 rounded-full bg-muted/50" />
                    </div>
                    <div className="grid grid-cols-4 border-t border-border/20 divide-x divide-border/15">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="flex flex-col items-center py-4 gap-2">
                                <div className="h-7 w-8 rounded bg-muted-foreground/12" />
                                <div className="h-2 w-10 rounded bg-muted-foreground/10" />
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <button
                onClick={handleShowTemplate}
                disabled={!template}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/25 bg-primary/8 text-primary/70 hover:bg-primary/12 hover:text-primary hover:border-primary/40 transition-colors text-xs disabled:opacity-40 disabled:cursor-not-allowed"
            >
                <PenLine size={11} className="shrink-0" />
                View template
            </button>
        </div>
    );
}
