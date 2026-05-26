import { BatchEmailJobCard } from "@/features/jobs/index";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { ConfirmDialog } from "@/shared/components/ui/dialog";
import { cn } from "@/shared/lib/utils";
import { Loader2, Mail, Plus, Target, Repeat } from "lucide-react";
import type { Tier } from "../types";
import { useOutreachContext } from "../context/OutreachContext";
import { CampaignCard } from "./CampaignCard";
import { SequenceCard } from "./SequenceCard";

export function CampaignListView() {
    const {
        listTab, setListTab,
        campaigns, loading,
        deleteTarget, setDeleteTarget,
        deleting, confirmDelete,
        openCampaign, setView, setGoal,
        expandedCard,
        setActiveCampaign,
        batchEmailJobs, loadingBatchEmailJobs,
        deleteBatchEmailTarget, setDeleteBatchEmailTarget,
        deletingBatchEmail, handleDeleteBatchEmail,
        sequences, loadingSequences, toggleSequence,
        deleteSeqTarget, setDeleteSeqTarget, deletingSeq, handleDeleteSequence,
        setBatchTier, setBatchFromDeepLink,
        enterBatch, enterQueue,
    } = useOutreachContext();

    return (
        <div className="p-6 space-y-6 w-full">
            <ConfirmDialog
                open={!!deleteTarget}
                onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
                title="Delete campaign?"
                description={
                    deleteTarget ? (
                        <>
                            Permanently deletes{" "}
                            <strong className="text-foreground/80">
                                "{deleteTarget.goal.slice(0, 60)}{deleteTarget.goal.length > 60 ? "…" : ""}"
                            </strong>{" "}
                            and all {deleteTarget.tier_1_count + deleteTarget.tier_2_count + deleteTarget.tier_3_count} scored contacts. Cannot be undone.
                        </>
                    ) : null
                }
                confirmLabel="Delete"
                onConfirm={confirmDelete}
                loading={deleting}
            />

            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <h1 className="text-xl font-bold tracking-tight">Outreach</h1>
                    <div className="flex items-center gap-0.5 bg-muted/50 border border-border/50 rounded-lg p-0.5">
                        <button
                            onClick={() => setListTab("campaigns")}
                            className={cn(
                                "px-3 py-1 text-xs font-mono font-medium rounded-md transition-all duration-150",
                                listTab === "campaigns"
                                    ? "bg-background text-foreground shadow-sm border border-border/60"
                                    : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            Campaigns
                        </button>
                        <button
                            onClick={() => setListTab("jobs")}
                            className={cn(
                                "px-3 py-1 text-xs font-mono font-medium rounded-md transition-all duration-150",
                                listTab === "jobs"
                                    ? "bg-background text-foreground shadow-sm border border-border/60"
                                    : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            Jobs
                        </button>
                        <button
                            onClick={() => setListTab("sequences")}
                            className={cn(
                                "px-3 py-1 text-xs font-mono font-medium rounded-md transition-all duration-150",
                                listTab === "sequences"
                                    ? "bg-background text-foreground shadow-sm border border-border/60"
                                    : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            Sequences
                        </button>
                    </div>
                </div>
                {listTab === "campaigns" && (
                    <Button onClick={() => { setGoal(""); setView("creating"); }} size="sm" className="gap-1.5 shrink-0">
                        <Plus size={13} /> New
                    </Button>
                )}
            </div>

            {listTab === "sequences" ? (
                loadingSequences && sequences.length === 0 ? (
                    <div className="space-y-3">
                        {[...Array(3)].map((_, i) => (
                            <div key={i} className="rounded-lg border overflow-hidden animate-pulse">
                                <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                                    <div className="h-3 w-12 rounded bg-muted/50" />
                                    <div className="h-3 flex-1 rounded bg-muted/40" />
                                </div>
                                <div className="px-4 py-5"><div className="h-8 rounded bg-muted/30" /></div>
                            </div>
                        ))}
                    </div>
                ) : sequences.length === 0 ? (
                    <Card className="py-12 px-8 flex flex-col items-center gap-4 text-center border-dashed max-w-sm">
                        <div className="h-10 w-10 rounded-xl bg-primary/8 flex items-center justify-center">
                            <Repeat size={20} className="text-primary" />
                        </div>
                        <div className="space-y-1">
                            <p className="text-xs font-mono font-medium uppercase tracking-widest text-muted-foreground">No sequences yet</p>
                            <p className="text-xs text-muted-foreground/60 max-w-xs leading-relaxed">
                                Open a tier's send panel and switch to <strong className="text-foreground/70">Sequence</strong> to launch a multi-touch follow-up campaign.
                            </p>
                        </div>
                    </Card>
                ) : (
                    <>
                        <ConfirmDialog
                            open={!!deleteSeqTarget}
                            onOpenChange={(open) => { if (!open) setDeleteSeqTarget(null); }}
                            title="Delete sequence?"
                            description="This stops the sequence and removes it along with all its enrollment progress. Emails already sent are not recalled."
                            confirmLabel="Delete"
                            onConfirm={handleDeleteSequence}
                            loading={deletingSeq}
                        />
                        <div className="space-y-3">
                            {sequences.map((seq) => (
                                <SequenceCard key={seq.id} seq={seq} onToggle={toggleSequence} onDelete={setDeleteSeqTarget} />
                            ))}
                        </div>
                    </>
                )
            ) : listTab === "jobs" ? (
                <>
                    <ConfirmDialog
                        open={!!deleteBatchEmailTarget}
                        onOpenChange={(open) => { if (!open) setDeleteBatchEmailTarget(null); }}
                        title="Remove job?"
                        description="This batch send job will be permanently removed."
                        confirmLabel="Remove"
                        onConfirm={() => { if (deleteBatchEmailTarget) handleDeleteBatchEmail(deleteBatchEmailTarget); }}
                        loading={deletingBatchEmail !== null}
                    />
                    {loadingBatchEmailJobs ? (
                        <div className="space-y-3">
                            {[...Array(3)].map((_, i) => (
                                <div key={i} className="rounded-lg border overflow-hidden animate-pulse">
                                    <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                                        <div className="h-2.5 w-2.5 rounded-full bg-muted/60" />
                                        <div className="h-3 w-12 rounded bg-muted/50" />
                                        <div className="h-3 flex-1 rounded bg-muted/40" />
                                    </div>
                                    <div className="px-4 py-4 space-y-2">
                                        <div className="h-1 rounded-full bg-muted/50" />
                                        <div className="h-8 rounded bg-muted/30" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : batchEmailJobs.length === 0 ? (
                        <Card className="py-12 px-8 flex flex-col items-center gap-4 text-center border-dashed max-w-sm">
                            <div className="h-10 w-10 rounded-xl bg-primary/8 flex items-center justify-center">
                                <Mail size={20} className="text-primary" />
                            </div>
                            <p className="text-xs font-mono font-medium uppercase tracking-widest text-muted-foreground">
                                No jobs yet
                            </p>
                        </Card>
                    ) : (
                        <div className="space-y-3">
                            {batchEmailJobs.map((job) => (
                                <BatchEmailJobCard
                                    key={job.id}
                                    job={job}
                                    onDelete={(j) => setDeleteBatchEmailTarget(j)}
                                    deleting={deletingBatchEmail === job.id}
                                    onTemplateClick={(j) => {
                                        const c = campaigns.find((c) => c.id === j.campaign_id);
                                        if (!c) return;
                                        setActiveCampaign(c);
                                        setBatchTier(j.tier as Tier);
                                        setBatchFromDeepLink(true);
                                        setView("batch");
                                    }}
                                />
                            ))}
                        </div>
                    )}
                </>
            ) : loading ? (
                <div className="space-y-3">
                    {[...Array(3)].map((_, i) => (
                        <div key={i} className="rounded-lg border overflow-hidden animate-pulse">
                            <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                                <div className="h-3 w-3 rounded bg-muted/60" />
                                <div className="h-4 w-14 rounded bg-muted/50" />
                                <div className="h-3 flex-1 rounded bg-muted/40" />
                                <div className="h-3 w-10 rounded bg-muted/30" />
                            </div>
                            <div className="px-4 py-3 space-y-2">
                                <div className="h-3 rounded bg-muted/50" style={{ width: `${70 + ((i * 11) % 20)}%` }} />
                                <div className="h-3 rounded bg-muted/35" style={{ width: `${45 + ((i * 9) % 25)}%` }} />
                            </div>
                            <div className="px-4 py-2.5 border-t border-border flex items-center gap-2">
                                <div className="h-3 w-3 rounded bg-muted/40" />
                                <div className="h-3 w-10 rounded bg-muted/35" />
                            </div>
                        </div>
                    ))}
                </div>
            ) : campaigns.length === 0 ? (
                <Card className="py-12 px-8 flex flex-col items-center gap-4 text-center border-dashed max-w-sm">
                    <div className="h-10 w-10 rounded-xl bg-primary/8 flex items-center justify-center">
                        <Target size={20} className="text-primary" />
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-mono font-medium uppercase tracking-widest text-muted-foreground">No campaigns yet</p>
                        <p className="text-xs text-muted-foreground/60 max-w-xs leading-relaxed">
                            Create a campaign to segment contacts by giving signals, wealth trajectory, and campaign relevance.
                        </p>
                    </div>
                    <Button onClick={() => setView("creating")} size="sm" className="gap-1.5">
                        <Plus size={13} /> Create Campaign
                    </Button>
                </Card>
            ) : (
                <div className="space-y-3">
                    {campaigns.map((c) => (
                        <CampaignCard
                            key={c.id}
                            campaign={c}
                            onOpen={() => openCampaign(c)}
                            onEnterTier={(tier) => enterQueue(tier, c)}
                            onEnterBatch={(tier) => enterBatch(tier, c)}
                            onDelete={() => setDeleteTarget(c)}
                            initialTiersOpen={expandedCard?.campaignId === c.id}
                            initialSelectedTier={expandedCard?.campaignId === c.id ? expandedCard.tier : null}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
