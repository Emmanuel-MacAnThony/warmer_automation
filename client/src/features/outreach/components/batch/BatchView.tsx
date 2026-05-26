import { type Campaign } from "@/shared/api/client";
import { ConfirmDialog } from "@/shared/components/ui/dialog";
import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Loader2, Mail, PenLine, Upload, X } from "lucide-react";
import { BatchCoreContext } from "../../context/batch/BatchCoreContext";
import { BatchEditorContext } from "../../context/batch/BatchEditorContext";
import { BatchSendContext } from "../../context/batch/BatchSendContext";
import { useBatchView } from "../../hooks/useBatchView";
import { TIER_ROWS } from "../../constants";
import type { BatchStep, Tier } from "../../types";
import { highlightSlots, sentenceCase } from "../../utils";
import { ChooseStep } from "./ChooseStep";
import { DetailsStep } from "./DetailsStep";
import { EditorStep } from "./EditorStep";

export function BatchView({
    campaign,
    tier,
    onBack,
    onJobQueued,
    initialStep = "choose",
}: {
    campaign: Campaign;
    tier: Tier;
    onBack: () => void;
    onJobQueued?: () => void;
    initialStep?: BatchStep;
}) {
    const { editorCtx, sendCtx, step, setStep } = useBatchView({
        campaign, tier, initialStep, onJobQueued,
    });

    const tierCfg = TIER_ROWS.find((r) => r.key === tier)!;
    const tierCount =
        tier === "tier_1" ? campaign.tier_1_count
        : tier === "tier_2" ? campaign.tier_2_count
        : campaign.tier_3_count;

    return (
        <BatchCoreContext.Provider value={{ campaign, tier, onBack, step, setStep }}>
        <BatchEditorContext.Provider value={editorCtx}>
        <BatchSendContext.Provider value={sendCtx}>
            <div className="flex h-full overflow-hidden relative">
                <div className="flex flex-col flex-1 min-w-0 min-h-0">
                    {/* Header */}
                    <div className="px-5 pt-4 pb-3 border-b border-border/40 shrink-0">
                        <div className="flex items-center gap-3">
                        <button
                            onClick={onBack}
                            className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
                        >
                            <ArrowLeft size={14} />
                        </button>
                        <div className="flex items-center gap-2 min-w-0">
                            <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-[11px] font-medium shrink-0", tierCfg.badge)}>
                                <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", tierCfg.dot)} />
                                {tierCfg.label}
                            </span>
                            <span className="text-xs text-muted-foreground/40 shrink-0">·</span>
                            <span className="text-xs font-mono text-muted-foreground tabular-nums shrink-0">{tierCount.toLocaleString()} contacts</span>
                            <span className="text-xs text-muted-foreground/40 shrink-0">·</span>
                            <span className="text-xs font-mono text-muted-foreground/60 truncate">{sentenceCase(campaign.goal)}</span>
                        </div>
                        <div className="ml-auto flex items-center gap-2 shrink-0">
                            {step === "editor" && editorCtx.hasTemplate && (
                                <>
                                    <input
                                        ref={editorCtx.fileInputRef}
                                        type="file"
                                        accept=".txt,.docx,.doc,.pdf"
                                        className="hidden"
                                        onChange={(e) => {
                                            const f = e.target.files?.[0];
                                            if (f) editorCtx.handleFileUpload(f);
                                            e.target.value = "";
                                        }}
                                    />
                                    <button
                                        onClick={() => editorCtx.fileInputRef.current?.click()}
                                        disabled={editorCtx.uploadingFile}
                                        className="h-7 px-2.5 rounded-md flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 border border-border/40 transition-colors disabled:opacity-30"
                                    >
                                        {editorCtx.uploadingFile ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                                        {editorCtx.uploadingFile ? "Parsing…" : "Upload"}
                                    </button>
                                    <button
                                        onClick={() => editorCtx.setShowPreview(!editorCtx.showPreview)}
                                        className={cn(
                                            "h-7 px-2.5 rounded-md flex items-center gap-1.5 text-xs border transition-colors",
                                            editorCtx.showPreview
                                                ? "bg-primary/10 border-primary/30 text-primary"
                                                : "border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/60",
                                        )}
                                    >
                                        <Mail size={11} /> Preview
                                    </button>
                                </>
                            )}
                        </div>
                        </div>
                        {campaign[`${tier}_insight` as keyof typeof campaign] && (
                            <div className="mt-6 relative">
                                <div
                                    className="absolute -top-2.5 left-0 z-10 h-5 flex items-center px-3 bg-emerald-500/15 text-[9px] font-mono uppercase tracking-widest text-emerald-400/60"
                                    style={{ clipPath: "polygon(0% 0%, calc(100% - 10px) 0%, 100% 100%, 0% 100%)" }}
                                >
                                    Tier summary
                                </div>
                                <div className="px-3 pt-3.5 pb-2 rounded-md bg-muted/40">
                                    <p className="text-[11px] font-mono leading-relaxed text-emerald-400/80">
                                        {campaign[`${tier}_insight` as keyof typeof campaign] as string}
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Step body */}
                    {step === "choose" ? (
                        <ChooseStep />
                    ) : step === "details" ? (
                        <DetailsStep />
                    ) : (
                        <EditorStep />
                    )}
                </div>

                {/* Template drawer (legacy) */}
                <AnimatePresence>
                    {sendCtx.showTplDrawer && (
                        <>
                            <motion.div
                                key="tpl-backdrop"
                                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                                transition={{ duration: 0.15 }}
                                onClick={() => sendCtx.setShowTplDrawer(false)}
                                className="absolute inset-0 bg-background/60 backdrop-blur-[2px] z-10"
                            />
                            <motion.div
                                key="tpl-drawer"
                                initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
                                transition={{ type: "spring", stiffness: 320, damping: 32 }}
                                className="absolute right-0 top-0 bottom-0 w-[420px] border-l border-border/40 bg-card bg-grid flex flex-col z-20 shadow-2xl"
                            >
                                <div className="px-5 py-3 border-b border-border/30 flex items-center justify-between shrink-0">
                                    <div className="flex items-center gap-2.5">
                                        <PenLine size={13} className="text-muted-foreground/60" />
                                        <p className="text-xs font-semibold text-foreground uppercase tracking-wide">Template</p>
                                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-border/40 text-muted-foreground/40 uppercase tracking-wide">read-only</span>
                                    </div>
                                    <button
                                        onClick={() => { sendCtx.setShowTplDrawer(false); sendCtx.setDrawerTemplate(null); }}
                                        className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                                    >
                                        <X size={13} />
                                    </button>
                                </div>
                                <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
                                    {!sendCtx.drawerTemplate ? (
                                        <div className="flex items-center justify-center py-12 text-xs text-muted-foreground gap-2">
                                            <Loader2 size={12} className="animate-spin" /> Loading…
                                        </div>
                                    ) : (
                                        <>
                                            {sendCtx.drawerTemplate.subject && (
                                                <div className="space-y-2">
                                                    <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/35">Subject</p>
                                                    <p className="text-[13px] font-mono text-foreground/80 leading-relaxed">
                                                        {highlightSlots(sendCtx.drawerTemplate.subject, new Set(editorCtx.airtableFields))}
                                                    </p>
                                                </div>
                                            )}
                                            {sendCtx.drawerTemplate.body && (
                                                <div className="space-y-2">
                                                    <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/35">Body</p>
                                                    <div
                                                        className={cn(
                                                            "text-[13px] leading-relaxed text-foreground/75",
                                                            "[&_h1]:text-base [&_h1]:font-bold [&_h1]:mb-2",
                                                            "[&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mb-1.5",
                                                            "[&_p]:mb-3 [&_p:last-child]:mb-0",
                                                            "[&_ul]:list-disc [&_ul]:pl-4 [&_ul]:mb-3",
                                                            "[&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:mb-3",
                                                            "[&_li]:mb-0.5 [&_strong]:font-semibold [&_em]:italic",
                                                        )}
                                                        dangerouslySetInnerHTML={{ __html: sendCtx.drawerTemplate.body }}
                                                    />
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            </motion.div>
                        </>
                    )}
                </AnimatePresence>

                {/* Cancel job confirmation */}
                <ConfirmDialog
                    open={sendCtx.confirmCancelJob}
                    onOpenChange={sendCtx.setConfirmCancelJob}
                    title="Cancel this batch job?"
                    description="Emails already sent will not be recalled. The job will stop immediately — any contacts not yet reached will remain unsent and you can start a new job later."
                    confirmLabel="Yes, cancel job"
                    confirmVariant="destructive"
                    onConfirm={sendCtx.handleCancelActiveJob}
                />

                {/* Preview drawer */}
                <AnimatePresence>
                    {editorCtx.showPreview && (
                        <>
                            <motion.div
                                key="preview-backdrop"
                                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                                transition={{ duration: 0.15 }}
                                onClick={() => editorCtx.setShowPreview(false)}
                                className="absolute inset-0 bg-background/60 backdrop-blur-[2px] z-10"
                            />
                            <motion.div
                                key="preview-drawer"
                                initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
                                transition={{ type: "spring", stiffness: 320, damping: 32 }}
                                className="absolute right-0 top-0 bottom-0 w-100 border-l border-border/40 bg-card bg-grid flex flex-col z-20 shadow-2xl"
                            >
                                <div className="px-5 py-3 border-b border-border/30 flex items-center justify-between shrink-0">
                                    <div className="flex items-center gap-3">
                                        <p className="text-xs font-medium text-foreground uppercase tracking-wide">Preview</p>
                                        {editorCtx.previews.length > 0 && (
                                            <div className="flex items-center gap-1">
                                                <button
                                                    onClick={() => editorCtx.setPreviewIdx(Math.max(0, editorCtx.previewIdx - 1))}
                                                    disabled={editorCtx.previewIdx === 0}
                                                    className="h-5 w-5 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-20"
                                                >‹</button>
                                                <span className="text-xs text-muted-foreground tabular-nums">
                                                    {editorCtx.previewIdx + 1} / {editorCtx.previews.length}
                                                </span>
                                                <button
                                                    onClick={() => editorCtx.setPreviewIdx(Math.min(editorCtx.previews.length - 1, editorCtx.previewIdx + 1))}
                                                    disabled={editorCtx.previewIdx === editorCtx.previews.length - 1}
                                                    className="h-5 w-5 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-20"
                                                >›</button>
                                            </div>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => editorCtx.setShowPreview(false)}
                                        className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                                    >
                                        <X size={13} />
                                    </button>
                                </div>
                                <div className="flex-1 overflow-y-auto px-6 py-5">
                                    {editorCtx.loadingPrev ? (
                                        <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
                                            <Loader2 size={11} className="animate-spin" /> Rendering…
                                        </div>
                                    ) : editorCtx.curPreview ? (
                                        <div className="space-y-5">
                                            <p className="font-mono text-xs text-muted-foreground/60">{editorCtx.curPreview.contact_name}</p>
                                            <div className="space-y-2">
                                                <p className="text-xs font-semibold text-foreground uppercase tracking-wide">Subject</p>
                                                <p className="font-mono text-[12px] font-normal leading-[1.8] text-muted-foreground">
                                                    {editorCtx.curPreview.rendered_subject || <span className="italic opacity-40">No subject</span>}
                                                </p>
                                            </div>
                                            <div className="border-t border-border/30" />
                                            <div className="space-y-2">
                                                <p className="text-xs font-semibold text-foreground uppercase tracking-wide">Body</p>
                                                {editorCtx.curPreview.rendered_body ? (
                                                    <div
                                                        className="font-mono text-[12px] font-normal leading-[1.8] text-muted-foreground [&_p]:mb-4 [&_p:last-child]:mb-0 [&_h1]:text-sm [&_h1]:font-semibold [&_h1]:text-foreground [&_h1]:mb-2 [&_h1]:mt-3 [&_h2]:text-[12px] [&_h2]:font-semibold [&_h2]:text-foreground [&_h2]:mb-1.5 [&_h2]:mt-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-3 [&_li]:mb-1 [&_strong]:font-semibold [&_strong]:text-foreground [&_em]:italic"
                                                        dangerouslySetInnerHTML={{ __html: editorCtx.curPreview.rendered_body }}
                                                    />
                                                ) : (
                                                    <span className="font-mono text-[12px] italic text-muted-foreground/40">No body</span>
                                                )}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex flex-col items-center justify-center h-full gap-3 py-16 text-center">
                                            <Mail size={22} className="text-muted-foreground/25" />
                                            <p className="text-sm text-muted-foreground">
                                                {(editorCtx.subject || editorCtx.body.replace(/<[^>]*>/g, "").trim())
                                                    ? "No contacts in this tier yet"
                                                    : "Add content to see the preview"}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </motion.div>
                        </>
                    )}
                </AnimatePresence>
            </div>
        </BatchSendContext.Provider>
        </BatchEditorContext.Provider>
        </BatchCoreContext.Provider>
    );
}
