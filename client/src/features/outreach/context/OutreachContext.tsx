import {
    type BatchEmailJob,
    type Campaign,
    type CampaignContact,
    type SegmentationEvent,
    type Sequence,
} from "@/shared/api/client";
import { createContext, useContext } from "react";
import type { Tier, View } from "../types";

export type OutreachContextValue = {
    // Navigation
    view: View;
    setView: (v: View) => void;
    listTab: "campaigns" | "jobs" | "sequences" | "suppressions";
    setListTab: (t: "campaigns" | "jobs" | "sequences" | "suppressions") => void;

    // Campaigns
    campaigns: Campaign[];
    loading: boolean;
    loadCampaigns: () => void;
    activeCampaign: Campaign | null;
    setActiveCampaign: (c: Campaign | null) => void;
    expandedCard: { campaignId: number; tier: Tier | null } | null;
    setExpandedCard: (v: { campaignId: number; tier: Tier | null } | null) => void;
    deleteTarget: Campaign | null;
    setDeleteTarget: (c: Campaign | null) => void;
    deleting: boolean;
    confirmDelete: () => void;
    openCampaign: (c: Campaign) => void;

    // Create campaign
    goal: string;
    setGoal: (v: string) => void;
    creating: boolean;
    handleCreate: (deck?: File) => void;

    // Batch email jobs
    batchEmailJobs: BatchEmailJob[];
    loadingBatchEmailJobs: boolean;
    deleteBatchEmailTarget: BatchEmailJob | null;
    setDeleteBatchEmailTarget: (j: BatchEmailJob | null) => void;
    deletingBatchEmail: number | null;
    handleDeleteBatchEmail: (job: BatchEmailJob) => void;

    // Sequences (cadence monitoring)
    sequences: Sequence[];
    loadingSequences: boolean;
    toggleSequence: (seq: Sequence) => void;
    deleteSeqTarget: Sequence | null;
    setDeleteSeqTarget: (s: Sequence | null) => void;
    deletingSeq: boolean;
    handleDeleteSequence: () => void;

    // Segmentation events
    segEvents: SegmentationEvent[];
    eventsEndRef: React.RefObject<HTMLDivElement | null>;

    // Queue
    queue: CampaignContact[];
    queueTotal: number;
    hasMore: boolean;
    loadingMore: boolean;
    sentinelRef: React.RefObject<HTMLDivElement | null>;
    queueIdx: number;
    setQueueIdx: (i: number) => void;
    actioning: boolean;
    showSignals: boolean;
    setShowSignals: (v: boolean) => void;
    activeTier: Tier;

    // Batch entry
    batchTier: Tier;
    setBatchTier: (t: Tier) => void;
    batchFromDeepLink: boolean;
    setBatchFromDeepLink: (v: boolean) => void;
    enterBatch: (tier: Tier, campaign?: Campaign) => void;
    enterQueue: (tier: Tier, campaign?: Campaign) => void;

    // Sidebar resize
    sidebarW: number;
    startDrag: (e: React.MouseEvent) => void;
};

export const OutreachContext = createContext<OutreachContextValue | null>(null);

export function useOutreachContext() {
    const ctx = useContext(OutreachContext);
    if (!ctx) throw new Error("useOutreachContext must be used inside Outreach");
    return ctx;
}
