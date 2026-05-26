import {
    type CampaignTemplate,
    type PreviewContact,
} from "@/shared/api/client";
import { createContext, useContext } from "react";

export type BatchEditorContextValue = {
    // Template
    template: CampaignTemplate | null;
    setTemplate: (t: CampaignTemplate | null) => void;
    subject: string;
    setSubject: (v: string) => void;
    body: string;
    setBody: (v: string) => void;
    dirty: boolean;
    setDirty: (v: boolean) => void;
    templateId: number | null;
    setTemplateId: (v: number | null) => void;
    hasTemplate: boolean;
    approved: boolean;

    // AI generation
    generating: boolean;
    guidance: string;
    setGuidance: (v: string) => void;
    guidanceHistory: string[];
    hadGuidance: boolean;
    dataWarning: string;
    // Node 1 — generate
    thinking: string;
    thinkDone: boolean;
    setThinking: (v: string) => void;
    setThinkDone: (v: boolean) => void;
    // Node 2 — critique
    critiqueText: string;
    setCritiqueText: (v: string) => void;
    critiqueDone: boolean;
    setCritiqueDone: (v: boolean) => void;
    critiqueScore: number | null;
    setCritiqueScore: (v: number | null) => void;
    // Node 3 — rewrite
    rewriteText: string;
    setRewriteText: (v: string) => void;
    rewriteDone: boolean;
    setRewriteDone: (v: boolean) => void;
    // Final quality score (persists after panels dismissed)
    finalScore: number | null;
    subjectVariants: string[];
    setSubjectVariants: (v: string[]) => void;
    thinkRef: React.RefObject<HTMLDivElement | null>;
    handleGenerate: () => void;
    handleCancel: () => void;

    // File upload
    fileInputRef: React.RefObject<HTMLInputElement | null>;
    uploadingFile: boolean;
    dragOver: boolean;
    setDragOver: (v: boolean) => void;
    handleFileUpload: (file: File) => void;

    // Variables / slots
    airtableFields: string[];
    enrichedFields: string[];
    varPopover: string | null;
    setVarPopover: (v: string | null) => void;
    fallbackInput: string;
    setFallbackInput: (v: string) => void;
    mapVariable: (from: string, to: string) => void;
    applyFallback: (varName: string, fallback: string) => void;

    // Preview drawer
    showPreview: boolean;
    setShowPreview: (v: boolean) => void;
    previews: PreviewContact[];
    previewIdx: number;
    setPreviewIdx: (v: number) => void;
    loadingPrev: boolean;
    curPreview: PreviewContact | null;
};

export const BatchEditorContext = createContext<BatchEditorContextValue | null>(null);

export function useBatchEditor() {
    const ctx = useContext(BatchEditorContext);
    if (!ctx) throw new Error("useBatchEditor must be used inside BatchView");
    return ctx;
}
