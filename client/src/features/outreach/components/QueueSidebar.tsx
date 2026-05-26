import { cn } from "@/shared/lib/utils";
import { ArrowLeft, Loader2, Mail } from "lucide-react";
import { useOutreachContext } from "../context/OutreachContext";

export function QueueSidebar() {
    const {
        activeCampaign, activeTier,
        setView, enterBatch,
        actioning, queue, queueIdx, setQueueIdx,
        queueTotal, sentinelRef, loadingMore, sidebarW,
    } = useOutreachContext();

    const tierLabel = activeTier === "tier_1" ? "Tier 1" : activeTier === "tier_2" ? "Tier 2" : "Tier 3";

    return (
        <div className="shrink-0 border-r flex flex-col overflow-hidden" style={{ width: sidebarW }}>
            <div className="px-4 py-3 border-b">
                <div className="flex items-center justify-between mb-1.5">
                    <button
                        onClick={() => setView("list")}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border border-emerald-500/25 bg-emerald-500/10 text-xs font-mono text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/15 transition-colors"
                    >
                        <ArrowLeft size={11} /> {tierLabel}
                    </button>
                    <button
                        onClick={() => enterBatch(activeTier)}
                        className="flex items-center gap-1 text-xs text-muted-foreground/40 hover:text-primary transition-colors"
                        title="Switch to Batch Mode"
                    >
                        <Mail size={11} /> Batch
                    </button>
                </div>
                <p className="text-xs text-muted-foreground/40 font-mono">
                    {queueIdx + 1} / {queueTotal || queue.length}
                </p>
            </div>
            <div className="flex-1 overflow-y-auto">
                {actioning && queue.length === 0
                    ? Array.from({ length: 9 }).map((_, i) => (
                        <div key={i} className="px-4 py-2.5 border-b">
                            <div className={cn("h-2.5 rounded-full bg-muted/50 animate-pulse mb-1.5", i % 3 === 0 ? "w-2/3" : i % 3 === 1 ? "w-3/4" : "w-1/2")} />
                            <div className={cn("h-2 rounded-full bg-muted/30 animate-pulse", i % 2 === 0 ? "w-1/2" : "w-2/5")} />
                        </div>
                    ))
                    : queue.map((c, i) => (
                        <button
                            key={c.id}
                            onClick={() => setQueueIdx(i)}
                            className={cn(
                                "w-full text-left px-4 py-2.5 border-b border-l-2 transition-colors",
                                i === queueIdx ? "bg-primary/5 border-l-primary" : "border-l-transparent hover:bg-muted/40",
                            )}
                        >
                            <div className="flex items-start justify-between gap-1.5">
                                <p className="text-xs text-foreground/75 truncate leading-snug">{c.contact_snapshot.name}</p>
                                <span className="text-xs font-mono text-muted-foreground/40 shrink-0 tabular-nums">
                                    {Math.round(c.composite_score * 100)}
                                </span>
                            </div>
                            <p className="text-xs text-muted-foreground/45 truncate mt-0.5">
                                {c.contact_snapshot.company || c.contact_snapshot.title || "—"}
                            </p>
                        </button>
                    ))}
                <div ref={sentinelRef} className="h-1" />
                {loadingMore && (
                    <div className="flex justify-center py-2.5">
                        <Loader2 size={12} className="animate-spin text-muted-foreground/30" />
                    </div>
                )}
            </div>
        </div>
    );
}
