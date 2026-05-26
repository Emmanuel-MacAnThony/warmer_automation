import {
    type BatchSendJob,
    type CampaignTemplate,
    type EmailProviderInfo,
    type GmailAccount,
    type ScopeCounts,
} from "@/shared/api/client";
import { createContext, useContext } from "react";

export type BatchSendContextValue = {
    // Connected accounts
    accounts: GmailAccount[];
    loadingAccounts: boolean;
    selectedAccounts: string[];
    toggleAccount: (email: string) => void;
    handleConnectAccount: () => void;
    handleDisconnectAccount: (email: string) => void;

    // Active outbound provider (gmail = per-account; smtp/resend = server-configured)
    emailProvider: EmailProviderInfo;

    // Test mode — redirects all sends to a single inbox
    testMode: boolean;
    setTestMode: (v: boolean) => void;

    // Send panel
    showSendPanel: boolean;
    setShowSendPanel: (v: boolean) => void;
    openSendPanel: () => void;
    scopeCounts: ScopeCounts | null;
    loadingScopes: boolean;
    queueingJob: boolean;
    handleQueueJob: () => void;

    // Sequence (cadence) builder
    sendMode: "single" | "sequence";
    setSendMode: (m: "single" | "sequence") => void;
    seqSteps: { template_id: number; subject: string; body: string; delay_days: number }[];
    addingStep: boolean;
    launchingSeq: boolean;
    addFollowUp: (delayDays: number) => void;
    updateSeqStep: (idx: number, patch: Partial<{ subject: string; body: string }>) => void;
    removeSeqStep: (idx: number) => void;
    setSeqStepDelay: (idx: number, days: number) => void;
    handleLaunchSequence: () => void;

    // Active job + pause / resume / cancel
    activeJob: BatchSendJob | null;
    jobIsActive: boolean;
    currentContact: string;
    pauseReason: string | null;
    setPauseReason: (v: string | null) => void;
    confirmCancelJob: boolean;
    setConfirmCancelJob: (v: boolean) => void;
    handlePauseJob: () => void;
    handleResumeJob: () => void;
    handleCancelActiveJob: () => void;

    // Template drawer
    showTplDrawer: boolean;
    setShowTplDrawer: (v: boolean) => void;
    drawerTemplate: CampaignTemplate | null;
    setDrawerTemplate: (t: CampaignTemplate | null) => void;
};

export const BatchSendContext = createContext<BatchSendContextValue | null>(null);

export function useBatchSend() {
    const ctx = useContext(BatchSendContext);
    if (!ctx) throw new Error("useBatchSend must be used inside BatchView");
    return ctx;
}
