import { Button } from "@/shared/components/ui/button";
import { CheckCircle2, Send, Telescope } from "lucide-react";
import { useOutreachContext } from "../context/OutreachContext";
import { QueueSidebar } from "./QueueSidebar";
import { ScoreWheel } from "./ScoreWheel";
import { SignalsDrawer } from "./SignalsDrawer";

export function QueueView() {
    const {
        queue, queueIdx, actioning,
        activeTier, setView, setShowSignals,
        enterBatch,
        sidebarW, startDrag,
    } = useOutreachContext();

    const tierLabel = activeTier === "tier_1" ? "Tier 1" : activeTier === "tier_2" ? "Tier 2" : "Tier 3";
    const contact = queue[queueIdx] ?? null;
    const snap = contact?.contact_snapshot;
    const score = contact?.score_breakdown;
    const signals = snap?.signals;

    return (
        <div className="flex h-full min-h-0">
            <QueueSidebar />
            <div
                onMouseDown={startDrag}
                className="w-1 shrink-0 cursor-col-resize hover:bg-primary/20 active:bg-primary/40 transition-colors"
            />
            <div className="flex-1 overflow-y-auto relative flex flex-col">
                {actioning && queue.length === 0 ? (
                    <div className="p-7 space-y-5 animate-pulse">
                        <div className="space-y-2">
                            <div className="h-4 w-2/5 rounded-full bg-muted/50" />
                            <div className="h-3 w-1/3 rounded-full bg-muted/30" />
                        </div>
                        <div className="rounded-xl border p-5 space-y-3">
                            <div className="h-2.5 w-1/4 rounded-full bg-muted/40" />
                            <div className="h-3 w-full rounded-full bg-muted/30" />
                            <div className="h-3 w-4/5 rounded-full bg-muted/30" />
                            <div className="h-3 w-3/5 rounded-full bg-muted/20" />
                        </div>
                    </div>
                ) : !contact ? (
                    <div className="flex flex-col items-center justify-center h-48 gap-4 text-center p-8">
                        <div className="h-10 w-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                            <CheckCircle2 size={20} className="text-emerald-500" />
                        </div>
                        <div>
                            <p className="text-xs font-mono font-medium uppercase tracking-widest text-muted-foreground">Queue complete</p>
                            <p className="text-xs text-muted-foreground/50 mt-1">All contacts reviewed</p>
                        </div>
                        <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" onClick={() => setView("list")}>Back</Button>
                            <Button size="sm" onClick={() => enterBatch(activeTier)}>
                                <Send size={11} className="mr-1.5" /> Batch send
                            </Button>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="flex flex-col h-full">
                            <div className="px-7 pt-7 pb-4 space-y-4">
                                <div className="space-y-1.5">
                                    <div className="flex items-start justify-between gap-3">
                                        <h2 className="text-base font-semibold text-foreground/85 leading-snug">{snap?.name ?? "—"}</h2>
                                        <div className="inline-flex items-center gap-1.5 shrink-0 px-2 py-1 rounded-md border border-emerald-500/25 bg-emerald-500/10">
                                            <div className="h-1.5 w-1.5 rounded-full shrink-0 bg-emerald-600 dark:bg-emerald-400" />
                                            <span className="text-xs font-mono text-emerald-600 dark:text-emerald-400">{tierLabel}</span>
                                            <span className="text-xs font-mono text-emerald-600/70 dark:text-emerald-400/55">
                                                · {Math.round(contact.composite_score * 100)}%
                                            </span>
                                        </div>
                                    </div>
                                    {(snap?.title || snap?.company) && (
                                        <p className="text-sm text-muted-foreground/55 leading-relaxed">
                                            {[snap?.title, snap?.company].filter(Boolean).join(" · ")}
                                        </p>
                                    )}
                                    {snap?.email && (
                                        <p className="text-sm text-muted-foreground/35 font-mono">{snap.email}</p>
                                    )}
                                    {((signals && Object.values(signals).some(Boolean)) || contact.warm_path_data?.connector) && (
                                        <button
                                            onClick={() => setShowSignals(true)}
                                            className="mt-2 flex items-center gap-1.5 text-sm font-medium text-emerald-500/70 hover:text-emerald-500 transition-colors"
                                        >
                                            <Telescope size={13} /> View Signals
                                        </button>
                                    )}
                                </div>
                                {/* Actions — temporarily hidden
                                <div className="flex flex-wrap gap-2">
                                  <Button onClick={handleSend} disabled={actioning || contact.status === 'sent'} className="gap-1.5 h-8 sm:h-9 text-xs sm:text-sm" size="sm">
                                    {actioning ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                                    {contact.status === 'sent' ? 'Sent' : 'Mark Sent'}
                                  </Button>
                                  <Button variant="outline" onClick={handleSkip} disabled={actioning} className="gap-1.5 h-8 sm:h-9 text-xs sm:text-sm" size="sm">
                                    <XCircle size={12} /> Skip
                                  </Button>
                                  <Button variant="outline" onClick={handleLater} disabled={actioning} className="gap-1.5 h-8 sm:h-9 text-xs sm:text-sm" size="sm">
                                    <Clock size={12} /> Later
                                  </Button>
                                </div>
                                */}
                            </div>
                            {score && (
                                <div className="px-7 pb-7 h-[15vh]">
                                    <ScoreWheel
                                        score={score}
                                        composite={contact.composite_score}
                                        onOpen={() => setShowSignals(true)}
                                    />
                                    {score.rag === 0 && (
                                        <p className="text-xs text-muted-foreground/40 mt-2">No match score — run Embedding first</p>
                                    )}
                                </div>
                            )}
                        </div>
                        <SignalsDrawer />
                    </>
                )}
            </div>
        </div>
    );
}
