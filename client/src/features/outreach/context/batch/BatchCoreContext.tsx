import type { Campaign } from "@/shared/api/client";
import { createContext, useContext } from "react";
import type { BatchStep, Tier } from "../../types";

export type BatchCoreContextValue = {
    campaign: Campaign;
    tier: Tier;
    onBack: () => void;
    step: BatchStep;
    setStep: (s: BatchStep) => void;
};

export const BatchCoreContext = createContext<BatchCoreContextValue | null>(null);

export function useBatchCore() {
    const ctx = useContext(BatchCoreContext);
    if (!ctx) throw new Error("useBatchCore must be used inside BatchView");
    return ctx;
}
