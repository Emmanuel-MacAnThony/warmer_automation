import { Button } from "@/shared/components/ui/button";
import { ConfirmDialog } from "@/shared/components/ui/dialog";
import { MaskedInput } from "@/shared/components/ui/masked-id";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { cn } from "@/shared/lib/utils";
import { AnimatePresence } from "framer-motion";
import { Plus, RefreshCw, Save } from "lucide-react";
import React from "react";
import { JobCard } from "./components/JobCard";
import { NewJobSheet } from "./components/NewJobSheet";
import { useJobs } from "./hooks/useJobs";

function SectionHeader({ icon: Icon, title, count }: { icon: React.ElementType; title: string; count?: number }) {
    return (
        <div className="flex items-center gap-2 mb-3">
            <Icon size={14} className="text-muted-foreground/60" />
            <span className="text-xs font-semibold tracking-widest uppercase text-muted-foreground/60 font-mono">
                {title}
            </span>
            {count != null && count > 0 && (
                <span className="ml-1 text-[10px] font-mono bg-muted text-muted-foreground/60 rounded px-1.5 py-0.5">
                    {count}
                </span>
            )}
            <div className="flex-1 border-t border-border/40 ml-1" />
        </div>
    );
}

export function Jobs() {
    const {
        config, isConfigured,
        draftBase, setDraftBase,
        draftTable, setDraftTable,
        saveConfig,
        jobs, batchMap, loading, error,
        acting,
        newJobOpen, setNewJobOpen,
        deleteJobTarget, setDeleteJobTarget,
        loadAll, handleDelete, handleAction,
    } = useJobs();

    return (
        <div className="flex flex-col h-full">
            {/* Sticky config bar */}
            <div className="sticky top-0 z-10 bg-background/90 backdrop-blur-md border-b border-border/60 px-6 py-4">
                <div className="flex items-end gap-3">
                    <div className="w-56 space-y-1.5">
                        <label className="text-sm text-muted-foreground font-medium">Base ID</label>
                        <MaskedInput
                            value={draftBase}
                            onChange={(e) => setDraftBase(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && saveConfig()}
                            placeholder="appXXXXXXXX"
                        />
                    </div>
                    <div className="w-56 space-y-1.5">
                        <label className="text-sm text-muted-foreground font-medium">Table ID</label>
                        <MaskedInput
                            value={draftTable}
                            onChange={(e) => setDraftTable(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && saveConfig()}
                            placeholder="tblXXXXXXXX"
                        />
                    </div>
                    <div className="flex items-center gap-2 pb-0.5">
                        <Button size="sm" onClick={saveConfig} disabled={!draftBase.trim() || !draftTable.trim()}>
                            <Save size={14} /> Load
                        </Button>
                        {isConfigured && (
                            <Button
                                variant="ghost" size="icon-sm"
                                onClick={() => void loadAll(config.baseId, config.tableId)}
                                disabled={loading}
                            >
                                <RefreshCw size={14} className={cn(loading && "animate-spin")} />
                            </Button>
                        )}
                    </div>
                    <div className="ml-auto pb-0.5">
                        {/* GlobalOutreachActions temporarily hidden — too much info in toolbar */}
                        <Button size="sm" onClick={() => setNewJobOpen(true)} disabled={!isConfigured}>
                            <Plus size={14} /> New Job
                        </Button>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-8">
                {!isConfigured && !loading && (
                    <p className="text-center py-20 text-base text-muted-foreground">
                        Enter a Base ID and Table ID above to load jobs.
                    </p>
                )}

                {isConfigured && (
                    <div>
                        <SectionHeader icon={RefreshCw} title="Enrichment Jobs" count={jobs.length} />

                        {loading && (
                            <div className="space-y-3">
                                {[...Array(2)].map((_, i) => (
                                    <div key={i} className="rounded-lg border border-border p-4 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <Skeleton className="h-4 w-20" />
                                            <Skeleton className="h-5 w-16 rounded-full" />
                                        </div>
                                        <Skeleton className="h-3 w-40" />
                                        <Skeleton className="h-2 w-full rounded-full" />
                                    </div>
                                ))}
                            </div>
                        )}

                        {error && <p className="text-sm text-red-400">{error}</p>}

                        {!loading && !error && jobs.length === 0 && (
                            <p className="text-sm text-muted-foreground py-4 pl-1">No enrichment jobs yet.</p>
                        )}

                        <div className="space-y-4">
                            <AnimatePresence>
                                {jobs.map((job) => (
                                    <JobCard
                                        key={job.id}
                                        job={job}
                                        batches={batchMap[job.id] ?? []}
                                        acting={acting === job.id}
                                        onAction={handleAction}
                                        onDelete={(id) => setDeleteJobTarget(id)}
                                        onRefresh={() => void loadAll(config.baseId, config.tableId, true)}
                                    />
                                ))}
                            </AnimatePresence>
                        </div>
                    </div>
                )}
            </div>

            <NewJobSheet
                open={newJobOpen}
                onOpenChange={setNewJobOpen}
                baseId={config.baseId}
                tableId={config.tableId}
                onCreated={() => void loadAll(config.baseId, config.tableId)}
            />

            <ConfirmDialog
                open={deleteJobTarget !== null}
                onOpenChange={(open) => { if (!open) setDeleteJobTarget(null); }}
                title="Delete enrichment job?"
                description="This job and all its data will be permanently deleted."
                confirmLabel="Delete"
                confirmVariant="destructive"
                onConfirm={async () => {
                    if (deleteJobTarget === null) return;
                    await handleDelete(deleteJobTarget);
                    setDeleteJobTarget(null);
                }}
            />
        </div>
    );
}

// Re-export for consumers that import from this feature root
export { BatchEmailJobCard } from "./components/BatchEmailJobCard";
export type { BatchEmailJobCardProps } from "./components/BatchEmailJobCard";
