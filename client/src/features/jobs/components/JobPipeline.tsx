import { api, type Batch, type DedupRun, type EmbeddingRun, type JobFailures, type WarmPathRun } from "@/shared/api/client";
import { Button } from "@/shared/components/ui/button";
import { toast } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronRight, Loader2, Pause, Play, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { BatchRow } from "./BatchRow";
import { DedupDonut } from "./DedupDonut";

interface JobPipelineProps {
    jobId: number;
    jobStatus: string;
    batches: Batch[];
    stats: { processed: number; hits: number; misses: number; failed: number };
    total: number;
    pct: number;
    onAction: () => void;
    acting: boolean;
    canAct: boolean;
    onRerun: () => void;
    rerunning: boolean;
}

function Dot({ done, active, failed }: { done: boolean; active: boolean; failed: boolean }) {
    return (
        <div className={cn(
            "w-6 h-6 rounded-full flex items-center justify-center shrink-0 border-2 transition-colors",
            done   ? "bg-primary border-primary" :
            active ? "border-primary bg-primary/10" :
            failed ? "bg-red-400 border-red-400" :
                     "border-muted-foreground/25 bg-background",
        )}>
            {done   ? <Check   size={12} className="text-white" /> :
             active ? <Loader2 size={11} className="animate-spin text-primary" /> :
             failed ? <X       size={11} className="text-white" /> :
             null}
        </div>
    );
}

const Connector = () => (
    <div className="flex flex-col items-center gap-0.75 my-1.5">
        <span className="w-1 h-1 rounded-full bg-muted-foreground/20" />
        <span className="w-1 h-1 rounded-full bg-muted-foreground/20" />
        <span className="w-1 h-1 rounded-full bg-muted-foreground/20" />
    </div>
);

function usePipelineStep<T extends { status: string; error?: string | null }>(
    fetch: () => Promise<T | null>,
    onComplete: string,
    onFail: (err: string) => string,
    keepPolling = false,   // poll even when run is null (e.g. job running but sub-run not yet created)
) {
    const [run, setRun] = useState<T | null | undefined>(undefined);
    const [triggering, setTriggering] = useState(false);
    // Only toast on a completion we actually witnessed go from active → done.
    // Prevents re-announcing an already-finished run every time the tab mounts.
    const sawActive = useRef(false);

    const refresh = useCallback(async () => {
        try { const r = await fetch(); setRun(r); return r; }
        catch { setRun(null); return null; }
    }, [fetch]);

    useEffect(() => { void refresh(); }, [refresh]);

    const active = run?.status === "running" || run?.status === "pending";
    const shouldPoll = active || (keepPolling && run == null);

    useEffect(() => {
        if (!shouldPoll) return;
        let cancelled = false;
        const tick = async () => {
            await new Promise(r => setTimeout(r, 2000));
            if (cancelled) return;
            const u = await refresh();
            if (u?.status === "running" || u?.status === "pending") sawActive.current = true;
            // Toast only if we saw this run in-flight first — not on a fresh mount
            // that happens to find a long-completed run.
            if (u?.status === "completed" && sawActive.current) toast.success(onComplete);
            if (u?.status === "failed"    && sawActive.current) toast.error(onFail(u.error ?? "unknown"));
            if (u?.status === "running" || u?.status === "pending" || (keepPolling && u == null)) tick();
        };
        tick();
        return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [shouldPoll]);

    return { run, active, triggering, setTriggering, refresh };
}

export function JobPipeline({
    jobId, jobStatus, batches, stats, total, pct,
    onAction, acting, canAct, onRerun, rerunning,
}: JobPipelineProps) {
    const [batchesOpen, setBatchesOpen] = useState(false);
    const [failuresOpen, setFailuresOpen] = useState(false);
    const [failures, setFailures] = useState<JobFailures | null>(null);
    const [loadingFailures, setLoadingFailures] = useState(false);

    const toggleFailures = async () => {
        const next = !failuresOpen;
        setFailuresOpen(next);
        if (next) {
            setLoadingFailures(true);
            try { setFailures(await api.getJobFailures(jobId)); }
            catch { /* surfaced as empty state */ }
            finally { setLoadingFailures(false); }
        }
    };

    const dedup = usePipelineStep(
        useCallback(() => api.dedupStatus(jobId),    [jobId]),
        "Health check — table is clean",
        (e) => `Health check failed: ${e}`,
        jobStatus === "running" || jobStatus === "pending",
    );
    const wp = usePipelineStep(
        useCallback(() => api.warmPathStatus(jobId), [jobId]),
        "Connections analysed — warm paths ready",
        (e) => `Connection analysis failed: ${e}`,
        jobStatus === "completed",
    );
    const emb = usePipelineStep(
        useCallback(() => api.embeddingStatus(jobId), [jobId]),
        "Contacts profiled — campaigns can now rank them by relevance",
        (e) => `Contact indexing failed: ${e}`,
        jobStatus === "completed",
    );

    const triggerStep = async (
        trigger: () => Promise<unknown>,
        refresh: () => Promise<unknown>,
        setTriggering: (v: boolean) => void,
    ) => {
        setTriggering(true);
        try { await trigger(); setTimeout(() => void refresh(), 600); }
        catch (e) { toast.error(String(e)); }
        finally { setTriggering(false); }
    };

    const dedupRun = dedup.run as (DedupRun | null | undefined);
    const wpRun    = wp.run    as (WarmPathRun | null | undefined);
    const embRun   = emb.run   as (EmbeddingRun | null | undefined);

    const dedupDone    = dedupRun?.status === "completed";
    const dedupFailed  = dedupRun?.status === "failed";
    const dedupDeleted = dedupRun?.records_deleted ?? 0;
    const dedupChecked = dedupRun?.records_checked ?? 0;
    const dedupGroups  = dedupRun?.groups_found    ?? 0;
    const dedupClean   = dedupDone && dedupDeleted === 0;

    const enrichDone    = jobStatus === "completed";
    const enrichRunning = (jobStatus === "running" || jobStatus === "pending") && (dedupDone || dedupFailed);

    const wpDone  = wpRun?.status  === "completed";
    const embDone = embRun?.status === "completed";

    const jobRunning     = jobStatus === "running" || jobStatus === "pending";
    const waitingForDedup = jobRunning && !dedupDone && !dedupFailed;

    // Inferred active states: show spinner whenever we know a step must be running
    // even if we haven't polled the run record yet (fast steps finish before first poll)
    const dedupActive = dedup.active || (dedupRun == null && jobRunning && !dedupFailed);
    const wpActive    = wp.active    || (wpRun    == null && enrichDone     && !wpDone);
    const embActive   = emb.active   || (embRun   == null && enrichDone     && !embDone);

    const wpProgress = (() => {
        if (!wp.active) return null;
        if (!wpRun?.contacts_loaded)
            return <p className="text-xs text-primary/70 mt-1 animate-pulse">Loading contacts…</p>;
        if (wpRun.paths_found == null)
            return (
                <p className="text-xs text-muted-foreground mt-1">
                    {wpRun.contacts_loaded.toLocaleString()} contacts loaded
                    {wpRun.targets_found != null && ` · ${wpRun.targets_found} targets found`}
                    <span className="text-primary/70 animate-pulse"> — finding paths…</span>
                </p>
            );
        return (
            <p className="text-xs text-muted-foreground mt-1">
                {wpRun.paths_found} paths found
                <span className="text-primary/70 animate-pulse"> — writing to Airtable…</span>
            </p>
        );
    })();

    const embProgress = (() => {
        if (!emb.active) return null;
        if (!embRun?.total_contacts)
            return <p className="text-xs text-primary/70 mt-1 animate-pulse">Fetching contacts…</p>;
        const newlyIndexed = embRun.indexed  ?? 0;
        const upToDate     = embRun.skipped  ?? 0;
        const processed    = newlyIndexed + upToDate;
        const embTotal     = embRun.total_contacts;
        const embPct       = Math.min(100, Math.round((processed / embTotal) * 100));
        return (
            <div className="mt-1.5 space-y-1.5">
                <div className="flex justify-between text-xs">
                    <span className="text-primary/70">Indexing…</span>
                    <span className="text-muted-foreground tabular-nums font-mono">
                        {processed.toLocaleString()} / {embTotal.toLocaleString()}
                    </span>
                </div>
                <div className="h-1 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-primary rounded-full transition-[width] duration-500"
                        style={{ width: `${embPct}%` }} />
                </div>
                {processed > 0 && (
                    <p className="text-xs text-muted-foreground font-mono">
                        {newlyIndexed > 0 && `${newlyIndexed.toLocaleString()} new`}
                        {newlyIndexed > 0 && upToDate > 0 && " · "}
                        {upToDate > 0 && `${upToDate.toLocaleString()} up to date`}
                    </p>
                )}
            </div>
        );
    })();

    const RunButton = ({
        done, active, running, onTrigger,
    }: { done: boolean; active: boolean; running: boolean; onTrigger: () => void }) => (
        !active ? (
            <Button size="sm" variant="outline" onClick={onTrigger} disabled={running}
                className="h-7 px-3 text-xs shrink-0 cursor-pointer gap-1.5">
                {running
                    ? <Loader2 size={11} className="animate-spin" />
                    : done
                        ? <><RefreshCw size={11} />Re-run</>
                        : <><Play size={11} />Run</>}
            </Button>
        ) : null
    );

    return (
        <div className="border-t border-border/50 px-4 pt-4 pb-3">

            {/* Step 1: Health check */}
            <div className="flex gap-3">
                <div className="flex flex-col items-center">
                    <Dot done={dedupDone} active={dedupActive} failed={dedupFailed} />
                    <Connector />
                </div>
                <div className="flex-1 min-w-0 pb-3">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <p className={cn("text-sm font-medium leading-none", dedupDone ? "text-muted-foreground/60" : "text-foreground/90")}>
                                Health check
                                {dedupDone && (
                                    <span className={cn("ml-2 text-xs font-mono font-normal", dedupClean ? "text-primary/70" : "text-amber-500")}>
                                        · {dedupClean ? "clean" : `${dedupDeleted} removed`}
                                    </span>
                                )}
                            </p>
                            {!dedupDone && !dedup.active && !dedupFailed && (
                                <p className="text-xs text-muted-foreground leading-relaxed mt-1">
                                    Finds and removes duplicate records before enrichment
                                </p>
                            )}
                            {dedupActive && (
                                <p className="text-xs text-primary/70 animate-pulse mt-1">
                                    {dedupRun?.records_checked != null
                                        ? `${dedupRun.records_checked.toLocaleString()} records scanned${dedupRun.groups_found ? ` · ${dedupRun.groups_found} groups found` : ''}…`
                                        : total > 0
                                            ? `Scanning ${total.toLocaleString()} records for duplicates…`
                                            : "Scanning for duplicates…"}
                                </p>
                            )}
                            {dedupFailed && (
                                <p className="text-xs text-red-400 mt-1">
                                    Failed — <button onClick={() => triggerStep(() => api.dedupRun(jobId), dedup.refresh, dedup.setTriggering)} className="underline cursor-pointer">try again</button>
                                </p>
                            )}
                            {dedupDone && dedupChecked > 0 && (
                                <div className="flex items-center gap-4 mt-2">
                                    <DedupDonut checked={dedupChecked} deleted={dedupDeleted} />
                                    <div className="flex gap-5">
                                        <div>
                                            <p className="text-sm font-semibold tabular-nums text-foreground/80">{dedupChecked.toLocaleString()}</p>
                                            <p className="font-mono text-[10px] text-muted-foreground/50 tracking-widest uppercase mt-0.5">Checked</p>
                                        </div>
                                        <div>
                                            <p className={cn("text-sm font-semibold tabular-nums", dedupDeleted > 0 ? "text-amber-500" : "text-primary")}>{dedupDeleted}</p>
                                            <p className="font-mono text-[10px] text-muted-foreground/50 tracking-widest uppercase mt-0.5">Removed</p>
                                        </div>
                                        {dedupGroups > 0 && (
                                            <div>
                                                <p className="text-sm font-semibold tabular-nums text-foreground/75">{dedupGroups}</p>
                                                <p className="font-mono text-[10px] text-muted-foreground/50 tracking-widest uppercase mt-0.5">Groups</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                        <RunButton
                            done={dedupDone} active={dedupActive} running={dedup.triggering}
                            onTrigger={() => triggerStep(() => api.dedupRun(jobId), dedup.refresh, dedup.setTriggering)}
                        />
                    </div>
                </div>
            </div>

            {/* Step 2: Batches (enrichment) */}
            <div className="flex gap-3">
                <div className="flex flex-col items-center">
                    <Dot done={enrichDone} active={enrichRunning} failed={jobStatus === "failed"} />
                    <Connector />
                </div>
                <div className={cn("flex-1 min-w-0 pb-3", waitingForDedup && "opacity-40 pointer-events-none")}>
                    {waitingForDedup ? (
                        <p className="text-xs text-muted-foreground mt-0.5 mb-3">Waiting for health check…</p>
                    ) : (
                        <>
                        <div className="h-1 rounded-full bg-muted overflow-hidden mb-1.5">
                            <motion.div className="h-full bg-primary rounded-full"
                                animate={{ width: `${pct}%` }}
                                transition={{ duration: 0.6, ease: "easeOut" }} />
                        </div>
                        <div className="flex items-center gap-4 text-sm mb-2">
                            <span className="font-semibold tabular-nums text-foreground">
                                {stats.processed}
                                {total > 0 && (
                                    <span className="text-muted-foreground">/{total.toLocaleString()} ({pct}%)</span>
                                )}
                            </span>
                            <span className="text-primary/70 tabular-nums">✓ {stats.hits}</span>
                            <span className="text-muted-foreground tabular-nums">— {stats.misses}</span>
                            {stats.failed > 0 ? (
                                <button
                                    onClick={toggleFailures}
                                    className="text-red-400 tabular-nums hover:text-red-300 underline underline-offset-2 decoration-red-400/30 hover:decoration-red-300 transition-colors"
                                    title="View failure reasons"
                                >
                                    ✗ {stats.failed}
                                </button>
                            ) : (
                                <span className="text-red-400 tabular-nums">✗ {stats.failed}</span>
                            )}
                        </div>
                        <AnimatePresence>
                            {failuresOpen && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: "auto", opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.2 }}
                                    className="overflow-hidden"
                                >
                                    <div className="rounded-md border border-red-500/20 bg-red-500/5 p-3 mb-2 space-y-2">
                                        {loadingFailures ? (
                                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                <Loader2 size={12} className="animate-spin" /> Reading failure reasons…
                                            </div>
                                        ) : !failures || failures.total_failed === 0 ? (
                                            <p className="text-xs text-muted-foreground/60">
                                                No failure details found (the batch files may have been cleared).
                                            </p>
                                        ) : (
                                            <>
                                                <p className="text-[10px] font-mono uppercase tracking-widest text-red-400/60">
                                                    Why {failures.total_failed} failed
                                                </p>
                                                <div className="space-y-1">
                                                    {failures.reasons.map((r) => (
                                                        <div key={r.reason} className="flex items-center justify-between gap-3 text-xs">
                                                            <span className="text-foreground/70">{r.reason}</span>
                                                            <span className="font-mono text-red-400/80 tabular-nums shrink-0">{r.count}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div className="max-h-40 overflow-y-auto border-t border-red-500/10 pt-2 mt-1 space-y-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:bg-border/30 [&::-webkit-scrollbar-thumb]:rounded-full">
                                                    {failures.records.map((rec) => (
                                                        <div key={rec.record_id} className="flex items-center justify-between gap-3 text-[11px] font-mono">
                                                            {rec.linkedin_url ? (
                                                                <a
                                                                    href={rec.linkedin_url}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    className="text-muted-foreground/60 hover:text-primary truncate transition-colors"
                                                                >
                                                                    {rec.linkedin_url.replace(/^https?:\/\/(www\.)?/, "")}
                                                                </a>
                                                            ) : (
                                                                <span className="text-muted-foreground/50 truncate">{rec.record_id}</span>
                                                            )}
                                                            <span className="text-muted-foreground/40 shrink-0 truncate max-w-[45%]">{rec.reason}</span>
                                                        </div>
                                                    ))}
                                                    {failures.truncated && (
                                                        <p className="text-[10px] text-muted-foreground/40 pt-1">
                                                            Showing first {failures.records.length} of {failures.total_failed}.
                                                        </p>
                                                    )}
                                                </div>
                                            </>
                                        )}
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                        </>
                    )}
                    <div className="flex items-center justify-between gap-2">
                        <button
                            onClick={() => setBatchesOpen(!batchesOpen)}
                            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                            <ChevronRight size={12} className={cn("transition-transform duration-150", batchesOpen && "rotate-90")} />
                            {batches.length > 0 ? `${batches.length} batches` : "Batches"}
                            {enrichRunning && (
                                <span className="flex items-center gap-1 text-primary/80 ml-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-primary/80 animate-pulse" /> live
                                </span>
                            )}
                        </button>
                        <div className="flex items-center gap-1">
                            {canAct && (
                                <Button variant="ghost" size="icon-sm" disabled={acting} onClick={onAction}>
                                    {acting
                                        ? <Loader2 size={12} className="animate-spin" />
                                        : jobStatus === "running"
                                            ? <Pause size={12} />
                                            : <Play size={12} />}
                                </Button>
                            )}
                            {jobStatus === "completed" && (
                                <Button variant="ghost" size="sm" disabled={rerunning} onClick={onRerun}
                                    className="h-7 px-2.5 text-xs text-muted-foreground hover:text-foreground gap-1.5">
                                    {rerunning ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                                    Re-run
                                </Button>
                            )}
                        </div>
                    </div>
                    <AnimatePresence>
                        {batchesOpen && (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.2 }}
                                className="overflow-hidden mt-2 -mx-4"
                            >
                                {batches.length === 0 ? (
                                    <div className="px-4 py-2 text-sm text-muted-foreground flex items-center gap-2">
                                        <Loader2 size={12} className="animate-spin" /> Loading batches…
                                    </div>
                                ) : (
                                    batches.map((b) => <BatchRow key={b.id} b={b} />)
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>

            {/* Step 3: Warm path */}
            <div className="flex gap-3">
                <div className="flex flex-col items-center">
                    <Dot done={wpDone} active={wpActive} failed={wpRun?.status === "failed"} />
                    <Connector />
                </div>
                <div className="flex-1 min-w-0 pb-3">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <p className={cn("text-sm font-medium leading-none", wpDone ? "text-muted-foreground/60" : "text-foreground/90")}>
                                Warm path analysis
                            </p>
                            {!wpDone && !wp.active && wpRun?.status !== "failed" && (
                                <p className="text-xs text-muted-foreground leading-relaxed mt-1">
                                    Finds warm intro paths between you and each contact via shared connections
                                </p>
                            )}
                            {wpActive && (wpProgress ?? <p className="text-xs text-primary/70 mt-1 animate-pulse">Running…</p>)}
                            {wpDone && <p className="text-xs text-muted-foreground mt-0.5">{wpRun?.paths_found ?? 0} paths found</p>}
                            {wpRun?.status === "failed" && (
                                <p className="text-xs text-red-400 mt-1">
                                    Failed — <button onClick={() => triggerStep(() => api.warmPathRun(jobId), wp.refresh, wp.setTriggering)} className="underline cursor-pointer">try again</button>
                                </p>
                            )}
                        </div>
                        <RunButton
                            done={wpDone} active={wpActive} running={wp.triggering}
                            onTrigger={() => triggerStep(() => api.warmPathRun(jobId), wp.refresh, wp.setTriggering)}
                        />
                    </div>
                </div>
            </div>

            {/* Step 4: Profile contacts */}
            <div className="flex gap-3">
                <div className="flex flex-col items-center">
                    <Dot done={embDone} active={embActive} failed={embRun?.status === "failed"} />
                </div>
                <div className="flex-1 min-w-0 pb-0.5">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <p className={cn("text-sm font-medium leading-none", embDone ? "text-muted-foreground/60" : "text-foreground/90")}>
                                Profile contacts
                            </p>
                            {!embDone && !emb.active && embRun?.status !== "failed" && (
                                <p className="text-xs text-muted-foreground leading-relaxed mt-1">
                                    Builds a profile of each contact so campaigns can rank them by relevance to your goal
                                </p>
                            )}
                            {embActive && (embProgress ?? <p className="text-xs text-primary/70 mt-1 animate-pulse">Running…</p>)}
                            {embDone && <p className="text-xs text-muted-foreground mt-0.5">{embRun?.indexed ?? 0} contacts indexed</p>}
                            {embRun?.status === "failed" && (
                                <p className="text-xs text-red-400 mt-1">
                                    Failed — <button onClick={() => triggerStep(() => api.embeddingRun(jobId), emb.refresh, emb.setTriggering)} className="underline cursor-pointer">try again</button>
                                </p>
                            )}
                        </div>
                        <RunButton
                            done={embDone} active={embActive} running={emb.triggering}
                            onTrigger={() => triggerStep(() => api.embeddingRun(jobId), emb.refresh, emb.setTriggering)}
                        />
                    </div>
                    {wpDone && embDone && (
                        <div className="flex items-center gap-2.5 mt-3 pt-2.5 border-t border-border/40">
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary/10 border border-primary/25 text-xs font-mono font-medium text-primary">
                                ✓ Ready for Outreach
                            </span>
                            <span className="text-xs font-mono text-muted-foreground/50">
                                {wpRun?.paths_found ?? 0} connections · {embRun?.indexed ?? 0} indexed
                            </span>
                        </div>
                    )}
                </div>
            </div>

        </div>
    );
}
