import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import {
    AlertTriangle,
    Check,
    ChevronRight,
    Loader2,
    Mail,
    Pencil,
    Plus,
    RefreshCw,
    Send,
    X,
} from "lucide-react";
import { useRef, useState } from "react";
import { FIELD_GROUPS, KNOWN_FIELDS } from "../../constants";
import { useBatchCore } from "../../context/batch/BatchCoreContext";
import { useBatchEditor } from "../../context/batch/BatchEditorContext";
import { useBatchSend } from "../../context/batch/BatchSendContext";
import { highlightSlots } from "../../utils";
import { SlotEditor } from "../SlotEditor";
import { VariablePicker } from "../VariablePicker";

export function EditorStep() {
    const {
        subject, setSubject,
        body, setBody,
        setDirty,
        generating,
        airtableFields,
        enrichedFields,
        varPopover, setVarPopover,
        fallbackInput, setFallbackInput,
        mapVariable, applyFallback,
        hasTemplate,
        guidance, setGuidance,
        guidanceHistory,
        dataWarning,
        subjectVariants, setSubjectVariants,
        finalScore,
        handleGenerate,
    } = useBatchEditor();

    const { setStep } = useBatchCore();
    const {
        accounts, loadingAccounts, selectedAccounts,
        toggleAccount, handleConnectAccount, handleDisconnectAccount,
        emailProvider,
        showSendPanel, setShowSendPanel, openSendPanel,
        scopeCounts, loadingScopes,
        queueingJob, handleQueueJob,
        sendMode, setSendMode,
        seqSteps, addingStep, launchingSeq,
        addFollowUp, updateSeqStep, removeSeqStep, setSeqStepDelay, handleLaunchSequence,
        activeJob, currentContact,
        testMode, setTestMode,
    } = useBatchSend();

    // Gmail uses per-account selection; smtp/resend send from a server-configured
    // address, so the account picker is hidden and queuing isn't gated on it.
    const needsAccount = emailProvider.requires_account;
    const canQueue = needsAccount ? selectedAccounts.length > 0 : true;

    const vars = [
        ...new Set([
            ...[...subject.matchAll(/\[([A-Za-z][A-Za-z0-9 _/.-]*)/g)].map((m) => m[1]),
            ...[...body.matchAll(/\[([A-Za-z][A-Za-z0-9 _/.-]*)/g)].map((m) => m[1]),
        ]),
    ];

    const jobPct = activeJob && activeJob.total > 0
        ? Math.round((activeJob.sent / activeJob.total) * 100) : 0;

    const [subjectSug, setSubjectSug] = useState<{ query: string; bracketIdx: number } | null>(null);
    const subjectInputRef = useRef<HTMLInputElement>(null);
    const [expandedStep, setExpandedStep] = useState<number | null>(null);

    const handleSubjectChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        const cursor = e.target.selectionStart ?? val.length;
        setSubject(val);
        setDirty(true);
        const textBefore = val.slice(0, cursor);
        const match = textBefore.match(/\[([^[\]]*)$/);
        if (match) {
            setSubjectSug({ query: match[1], bracketIdx: cursor - match[0].length });
        } else {
            setSubjectSug(null);
        }
    };

    const insertSubjectField = (field: string) => {
        if (!subjectSug) return;
        const { bracketIdx, query } = subjectSug;
        const before = subject.slice(0, bracketIdx);
        const after = subject.slice(bracketIdx + 1 + query.length);
        const newVal = `${before}[${field}]${after}`;
        setSubject(newVal);
        setDirty(true);
        setSubjectSug(null);
        setTimeout(() => {
            if (subjectInputRef.current) {
                const pos = before.length + field.length + 2;
                subjectInputRef.current.focus();
                subjectInputRef.current.setSelectionRange(pos, pos);
            }
        }, 0);
    };

    return (
        <div className="flex flex-col flex-1 min-h-0 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border/30 [&::-webkit-scrollbar-thumb]:rounded-full">
            {/* Active job banner — click to jump to DetailsStep */}
            {activeJob && (activeJob.status === "running" || activeJob.status === "pending" || activeJob.status === "paused") && (
                <button
                    onClick={() => setStep("details")}
                    className={cn(
                        "w-full flex items-center gap-3 px-4 py-2.5 border-b text-left transition-colors",
                        activeJob.status === "paused"
                            ? "border-amber-500/20 bg-amber-500/5 hover:bg-amber-500/10"
                            : "border-primary/20 bg-primary/5 hover:bg-primary/8",
                    )}
                >
                    <div className={cn(
                        "h-1.5 w-1.5 rounded-full shrink-0",
                        activeJob.status === "paused" ? "bg-amber-400" : "bg-primary/70 animate-pulse",
                    )} />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                            <span className={cn(
                                "text-[10px] font-mono font-semibold uppercase tracking-widest",
                                activeJob.status === "paused" ? "text-amber-400" : "text-primary/70",
                            )}>
                                {activeJob.status === "paused" ? "Paused" : "Sending"} — {activeJob.sent.toLocaleString()} / {activeJob.total.toLocaleString()}
                                {currentContact && activeJob.status === "running" && ` · ${currentContact}`}
                            </span>
                            <span className="text-[10px] font-mono text-muted-foreground/40 shrink-0">View →</span>
                        </div>
                        <div className="h-1 bg-muted/30 rounded-full overflow-hidden">
                            <motion.div
                                className={cn("h-full rounded-full", activeJob.status === "paused" ? "bg-amber-400/50" : "bg-primary/50")}
                                initial={false}
                                animate={{ width: `${jobPct}%` }}
                                transition={{ duration: 0.5, ease: "easeOut" }}
                            />
                        </div>
                    </div>
                </button>
            )}

            {/* Subject */}
            <div className="px-6 pt-4 pb-2 shrink-0">
                <label className="block text-[11px] font-mono font-semibold tracking-widest uppercase text-muted-foreground/60 mb-1.5">Subject</label>
                <div
                    className={cn(
                        "relative rounded-md border border-border/50 bg-card focus-within:ring-1 focus-within:ring-ring/40",
                        generating && "pointer-events-none border-primary/30",
                    )}
                >
                    <div
                        aria-hidden
                        className="absolute inset-0 px-3 py-2.5 text-[13px] font-mono text-muted-foreground pointer-events-none select-none overflow-hidden rounded-md whitespace-pre-wrap"
                    >
                        {subject ? (
                            highlightSlots(subject, new Set(airtableFields))
                        ) : (
                            <span className="text-muted-foreground/30">Email subject line…</span>
                        )}
                    </div>
                    <input
                        ref={subjectInputRef}
                        value={subject}
                        onChange={handleSubjectChange}
                        onKeyDown={(e) => { if (e.key === "Escape" && subjectSug) { e.preventDefault(); setSubjectSug(null); } }}
                        onBlur={() => setSubjectSug(null)}
                        disabled={generating}
                        className="relative w-full px-3 py-2.5 text-[13px] font-mono bg-transparent text-transparent caret-foreground border-0 focus:outline-none focus:ring-0 rounded-md"
                    />
                </div>
                {subjectSug && subjectInputRef.current && (
                    <VariablePicker
                        query={subjectSug.query}
                        anchorRect={subjectInputRef.current.getBoundingClientRect()}
                        onSelect={insertSubjectField}
                        onClose={() => setSubjectSug(null)}
                        enrichedFields={enrichedFields}
                    />
                )}
            </div>

            {/* Subject variants */}
            {subjectVariants.length > 0 && (
                <div className="px-6 pb-2 shrink-0">
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground/60 font-medium mb-1.5">Subject alternatives</p>
                    <div className="flex flex-wrap gap-1.5">
                        {subjectVariants.map((v, i) => (
                            <button
                                key={i}
                                onClick={() => { setSubject(v); setDirty(true); setSubjectVariants([]); }}
                                className={cn(
                                    "px-2.5 py-1 rounded-md text-[11px] font-mono border transition-colors text-left",
                                    v === subject
                                        ? "border-primary/40 bg-primary/10 text-primary"
                                        : "border-border/40 bg-muted/30 text-foreground/70 hover:bg-muted/60 hover:text-foreground hover:border-border/60",
                                )}
                            >
                                {v}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Body */}
            <div className="px-6 pb-1 shrink-0">
                <label className="block text-[11px] font-mono font-semibold tracking-widest uppercase text-muted-foreground/60">Body</label>
            </div>
            <div className="px-6 pb-2 shrink-0">
                <SlotEditor
                    value={body}
                    onChange={(v) => { setBody(v); setDirty(true); }}
                    disabled={generating}
                    placeholder="Email body…"
                    knownSet={new Set(airtableFields)}
                    enrichedFields={enrichedFields}
                />
            </div>

            {/* Variables + bottom bar */}
            <div>
                {vars.length > 0 && (
                    <div className="px-6 pt-4 pb-3 border-t border-border/30 shrink-0">
                        <label className="text-[11px] font-mono font-semibold tracking-widest uppercase text-muted-foreground/60">Variables</label>
                        <div className="flex flex-wrap gap-2 mt-1.5">
                            {vars.map((v) => {
                                const mapped = v in KNOWN_FIELDS || airtableFields.includes(v);
                                const open = varPopover === v;
                                const esc = v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
                                const hasFb = new RegExp(`\\[${esc}\\s*\\|\\s*fallback:`, "i").test(subject + "\n" + body);
                                const colors = mapped
                                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/50"
                                    : hasFb
                                      ? "border-blue-500/30 bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 hover:border-blue-500/50"
                                      : "border-amber-500/30 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 hover:border-amber-500/50";
                                return (
                                    <button
                                        key={v}
                                        onClick={() => {
                                            if (open) { setVarPopover(null); setFallbackInput(""); return; }
                                            setVarPopover(v);
                                            const m = (subject + "\n" + body).match(
                                                new RegExp(`\\[${esc}\\s*\\|\\s*fallback:\\s*"([^"]*)"`, "i"),
                                            );
                                            setFallbackInput(m ? m[1] : "");
                                        }}
                                        className={cn(
                                            "inline-flex items-center rounded-full border text-[11px] font-mono transition-all active:scale-95",
                                            open && "ring-1 ring-ring/30",
                                            colors,
                                        )}
                                    >
                                        <span className="pl-3.5 pr-2 py-1.5 leading-none">{v}</span>
                                        <ChevronRight size={10} className="mr-3 opacity-40" />
                                    </button>
                                );
                            })}
                        </div>

                        {varPopover && (
                            <div className="rounded-md border border-border/40 bg-card p-3 space-y-3 mt-2">
                                <div className="flex items-center justify-between">
                                    <span className="text-xs font-mono font-medium text-foreground">{`[${varPopover}]`}</span>
                                    <button
                                        onClick={() => { setVarPopover(null); setFallbackInput(""); }}
                                        className="text-muted-foreground/40 hover:text-muted-foreground transition-colors"
                                    >
                                        <X size={11} />
                                    </button>
                                </div>
                                <div className="space-y-1.5">
                                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
                                        Fallback if missing
                                    </p>
                                    <div className="flex gap-1.5">
                                        <input
                                            autoFocus
                                            value={fallbackInput}
                                            onChange={(e) => setFallbackInput(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter") applyFallback(varPopover, fallbackInput);
                                            }}
                                            placeholder="leave blank to omit"
                                            className="flex-1 px-2.5 py-1.5 text-[12px] font-mono bg-background border border-border/50 rounded-md text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:ring-1 focus:ring-ring/30"
                                        />
                                        <button
                                            onClick={() => applyFallback(varPopover, fallbackInput)}
                                            className="px-3 py-1.5 rounded-md bg-primary/10 hover:bg-primary/20 text-primary text-[11px] font-medium border border-primary/20 shrink-0"
                                        >
                                            Set
                                        </button>
                                    </div>
                                </div>
                                <div className="space-y-1.5">
                                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
                                        Map to field
                                    </p>
                                    <div className="flex flex-wrap gap-1">
                                        {enrichedFields.length > 0 && (
                                            <div className="w-full">
                                                <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-1 mt-1.5">Enriched</p>
                                                <div className="flex flex-wrap gap-1">
                                                    {enrichedFields.map((f) => (
                                                        <button
                                                            key={f}
                                                            onClick={() => mapVariable(varPopover, f)}
                                                            className="px-2 py-0.5 rounded text-[11px] font-mono bg-muted/50 hover:bg-muted text-foreground/70 hover:text-foreground transition-colors"
                                                        >
                                                            {f}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {Object.entries(FIELD_GROUPS).map(([group, fields]) => (
                                            <div key={group} className="w-full">
                                                <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-1 mt-1.5">{group}</p>
                                                <div className="flex flex-wrap gap-1">
                                                    {fields.map((f) => (
                                                        <button
                                                            key={f}
                                                            onClick={() => mapVariable(varPopover, f)}
                                                            className="px-2 py-0.5 rounded text-[11px] font-mono bg-muted/50 hover:bg-muted text-foreground/70 hover:text-foreground transition-colors"
                                                        >
                                                            {f}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}

                    </div>
                )}

                {/* Bottom bar */}
                <div className="border-t border-border/40 px-6 py-2 space-y-2 w-full shrink-0">
                    <AnimatePresence>
                        {showSendPanel && (
                            <motion.div
                                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }}
                                transition={{ duration: 0.15 }}
                                className="rounded-md border border-border/50 bg-card p-4 space-y-3"
                            >
                                <div className="flex items-center justify-between">
                                    <p className="text-[12px] font-semibold text-foreground">
                                        {sendMode === "sequence" ? "Send a sequence" : "Send batch email"}
                                    </p>
                                    <button
                                        onClick={() => setShowSendPanel(false)}
                                        className="h-5 w-5 rounded flex items-center justify-center text-muted-foreground/40 hover:text-muted-foreground hover:bg-muted transition-colors"
                                    >
                                        <X size={11} />
                                    </button>
                                </div>

                                {/* Single vs Sequence toggle */}
                                <div className="grid grid-cols-2 gap-1 p-0.5 rounded-md bg-muted/40 border border-border/40">
                                    {(["single", "sequence"] as const).map((m) => (
                                        <button
                                            key={m}
                                            onClick={() => setSendMode(m)}
                                            className={cn(
                                                "py-1.5 rounded text-[11px] font-medium transition-colors",
                                                sendMode === m
                                                    ? "bg-primary/15 text-primary"
                                                    : "text-muted-foreground/60 hover:text-foreground",
                                            )}
                                        >
                                            {m === "single" ? "Single send" : "Sequence"}
                                        </button>
                                    ))}
                                </div>

                                {/* Sequence steps */}
                                {sendMode === "sequence" && (
                                    <div className="space-y-1.5">
                                        <p className="text-[10px] uppercase tracking-wide text-muted-foreground/40 font-medium">Steps</p>
                                        <div className="rounded-md border border-border/40 bg-muted/10 px-3 py-2 flex items-center gap-2">
                                            <span className="h-5 w-5 rounded-full bg-primary/15 text-primary text-[10px] font-mono flex items-center justify-center shrink-0">1</span>
                                            <span className="flex-1 text-[12px] text-foreground/80 truncate">This email</span>
                                            <span className="text-[10px] font-mono text-muted-foreground/50 shrink-0">now</span>
                                        </div>
                                        {seqSteps.map((s, i) => (
                                            <div key={i} className="rounded-md border border-border/40 bg-muted/10 overflow-hidden">
                                                <div className="px-3 py-2 flex items-center gap-2">
                                                    <span className="h-5 w-5 rounded-full bg-primary/15 text-primary text-[10px] font-mono flex items-center justify-center shrink-0">{i + 2}</span>
                                                    <button
                                                        onClick={() => setExpandedStep(expandedStep === i ? null : i)}
                                                        className="flex-1 min-w-0 flex items-center gap-1.5 text-left"
                                                        title="Click to preview"
                                                    >
                                                        <ChevronRight size={11} className={cn("shrink-0 text-muted-foreground/40 transition-transform", expandedStep === i && "rotate-90")} />
                                                        <span className="text-[12px] text-foreground/70 truncate">{s.subject || "Follow-up"}</span>
                                                    </button>
                                                    <span className="text-[10px] font-mono text-muted-foreground/50 shrink-0">after</span>
                                                    <input
                                                        type="number" min={1} value={s.delay_days}
                                                        onChange={(e) => setSeqStepDelay(i, parseInt(e.target.value) || 1)}
                                                        className="w-10 text-center text-[12px] font-mono bg-background border border-border/50 rounded px-1 py-0.5 focus:outline-none focus:border-primary/40"
                                                    />
                                                    <span className="text-[10px] font-mono text-muted-foreground/50 shrink-0">days</span>
                                                    <button onClick={() => removeSeqStep(i)} className="text-muted-foreground/30 hover:text-red-400 transition-colors shrink-0">
                                                        <X size={12} />
                                                    </button>
                                                </div>
                                                {expandedStep === i && (
                                                    <div className="border-t border-border/30 bg-background/40 px-3 py-2.5 space-y-2">
                                                        <div>
                                                            <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-1">Subject</p>
                                                            <input
                                                                value={s.subject}
                                                                onChange={(e) => updateSeqStep(i, { subject: e.target.value })}
                                                                placeholder="Subject line…"
                                                                className="w-full text-[12px] font-mono bg-background border border-border/50 rounded-md px-2.5 py-1.5 focus:outline-none focus:border-primary/40 text-foreground/85 placeholder:text-muted-foreground/30"
                                                            />
                                                        </div>
                                                        <div>
                                                            <p className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-1">Body</p>
                                                            <SlotEditor
                                                                value={s.body}
                                                                onChange={(v) => updateSeqStep(i, { body: v })}
                                                                placeholder="Follow-up body…"
                                                                knownSet={new Set(airtableFields)}
                                                                enrichedFields={enrichedFields}
                                                            />
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                        <button
                                            onClick={() => addFollowUp(3)}
                                            disabled={addingStep}
                                            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-md border border-dashed border-border/40 text-[11px] text-muted-foreground/50 hover:text-foreground/70 hover:border-border/60 transition-colors disabled:opacity-40"
                                        >
                                            {addingStep ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                                            {addingStep ? "Writing follow-up…" : "Add follow-up (AI-written)"}
                                        </button>
                                        <p className="text-[10px] text-muted-foreground/40 leading-relaxed">
                                            Each contact gets these in order, spaced by the delays. A contact's sequence stops automatically once they reply (Gmail).
                                        </p>
                                    </div>
                                )}

                                {/* Server-configured provider (smtp / resend) — no account picker */}
                                {!needsAccount && (
                                    <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5 flex items-center gap-2.5">
                                        <div className="h-7 w-7 rounded-md flex items-center justify-center shrink-0 bg-emerald-500/15 text-emerald-400">
                                            <Mail size={13} />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-[12px] text-foreground/80">
                                                Sending via <span className="font-medium capitalize">{emailProvider.provider}</span>
                                            </p>
                                            {emailProvider.from_email && (
                                                <p className="text-[11px] font-mono text-muted-foreground/50 truncate">{emailProvider.from_email}</p>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {/* Sender accounts — Gmail only */}
                                {needsAccount && (
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <p className="text-[10px] uppercase tracking-wide text-muted-foreground/40 font-medium">
                                            Sender accounts
                                        </p>
                                        {loadingAccounts && <Loader2 size={10} className="animate-spin text-muted-foreground/30" />}
                                    </div>

                                    {accounts.length === 0 && !loadingAccounts && (
                                        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5 flex items-center gap-2.5">
                                            <div className="h-7 w-7 rounded-md flex items-center justify-center shrink-0 bg-amber-500/15 text-amber-400">
                                                <Mail size={13} />
                                            </div>
                                            <span className="flex-1 text-[12px] text-amber-400/70">Connect Gmail to send from your inbox</span>
                                            <button
                                                onClick={handleConnectAccount}
                                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors shrink-0"
                                            >
                                                <Mail size={10} /> Connect Gmail
                                            </button>
                                        </div>
                                    )}

                                    {accounts.map((account) => {
                                        const selected = selectedAccounts.includes(account.email);
                                        return (
                                            <div
                                                key={account.email}
                                                onClick={() => toggleAccount(account.email)}
                                                className={cn(
                                                    "rounded-md border px-3 py-2 flex items-center gap-2.5 cursor-pointer transition-colors",
                                                    selected
                                                        ? "border-emerald-500/20 bg-emerald-500/5 hover:bg-emerald-500/8"
                                                        : "border-border/40 bg-muted/10 hover:bg-muted/20",
                                                )}
                                            >
                                                <div className={cn(
                                                    "h-4 w-4 rounded border flex items-center justify-center shrink-0 transition-colors",
                                                    selected ? "border-emerald-500/60 bg-emerald-500/20" : "border-border/50",
                                                )}>
                                                    {selected && <Check size={9} className="text-emerald-400" />}
                                                </div>
                                                <div className="h-6 w-6 rounded flex items-center justify-center shrink-0 bg-emerald-500/10 text-emerald-400">
                                                    <Mail size={11} />
                                                </div>
                                                <span className="flex-1 text-[12px] font-mono text-foreground/80 truncate">{account.email}</span>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDisconnectAccount(account.email); }}
                                                    className="text-[11px] text-muted-foreground/30 hover:text-red-400 transition-colors shrink-0"
                                                >
                                                    Disconnect
                                                </button>
                                            </div>
                                        );
                                    })}

                                    {accounts.length > 0 && (
                                        <button
                                            onClick={handleConnectAccount}
                                            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-md text-[11px] font-medium border border-dashed border-border/40 text-muted-foreground/40 hover:text-foreground/60 hover:border-border/60 hover:bg-muted/10 transition-colors"
                                        >
                                            <Plus size={11} /> Add another account
                                        </button>
                                    )}
                                </div>
                                )}

                                {/* Test mode toggle */}
                                <button
                                    onClick={() => setTestMode(!testMode)}
                                    className={cn(
                                        "w-full flex items-center gap-2.5 rounded-md border px-3 py-2 transition-colors text-left",
                                        testMode
                                            ? "border-violet-500/30 bg-violet-500/8"
                                            : "border-border/30 bg-muted/10 hover:bg-muted/20",
                                    )}
                                >
                                    <div className={cn(
                                        "h-4 w-4 rounded border flex items-center justify-center shrink-0 transition-colors",
                                        testMode ? "border-violet-500/60 bg-violet-500/20" : "border-border/50",
                                    )}>
                                        {testMode && <Check size={9} className="text-violet-400" />}
                                    </div>
                                    <span className={cn(
                                        "text-[11px] font-mono flex-1",
                                        testMode ? "text-violet-300/80" : "text-muted-foreground/50",
                                    )}>
                                        Test mode — send all copies to <span className="font-semibold">macanthonyemmanuel9@gmail.com</span>
                                    </span>
                                </button>

                                {loadingScopes && (
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                        <Loader2 size={11} className="animate-spin" /> Loading…
                                    </div>
                                )}

                                <div className="flex items-center gap-2 pt-1">
                                    <button
                                        onClick={() => setShowSendPanel(false)}
                                        className="h-7 w-7 rounded-md flex items-center justify-center text-muted-foreground/40 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                    >
                                        <X size={13} />
                                    </button>
                                    {sendMode === "sequence" ? (
                                        <button
                                            onClick={handleLaunchSequence}
                                            disabled={launchingSeq || addingStep || !canQueue}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium border transition-colors disabled:opacity-30 bg-primary/10 border-primary/30 text-primary hover:bg-primary/20"
                                        >
                                            {launchingSeq ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
                                            {launchingSeq ? "Launching…" : `Launch sequence (${seqSteps.length + 1} step${seqSteps.length ? "s" : ""})`}
                                        </button>
                                    ) : (
                                        <button
                                            onClick={handleQueueJob}
                                            disabled={queueingJob || loadingScopes || !canQueue || (scopeCounts ? scopeCounts.everyone === 0 : true)}
                                            className={cn(
                                                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium border transition-colors disabled:opacity-30",
                                                testMode
                                                    ? "bg-violet-500/10 border-violet-500/30 text-violet-300 hover:bg-violet-500/20"
                                                    : "bg-primary/10 border-primary/30 text-primary hover:bg-primary/20",
                                            )}
                                        >
                                            {queueingJob ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
                                            {queueingJob
                                                ? "Queuing…"
                                                : testMode
                                                    ? `Test ${scopeCounts ? scopeCounts.everyone.toLocaleString() : "…"} emails → you`
                                                            : `Queue ${scopeCounts ? scopeCounts.everyone.toLocaleString() : "…"} emails`}
                                        </button>
                                    )}
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Guidance history chips */}
                    {guidanceHistory.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                            {guidanceHistory.slice(-3).map((g, i) => (
                                <span
                                    key={i}
                                    className="px-2 py-0.5 rounded-full text-[10px] font-mono border border-border/30 bg-muted/30 text-muted-foreground/50 truncate max-w-50"
                                    title={g}
                                >
                                    {g.length > 40 ? g.slice(0, 40) + "…" : g}
                                </span>
                            ))}
                        </div>
                    )}

                    <textarea
                        value={guidance}
                        onChange={(e) => setGuidance(e.target.value)}
                        disabled={generating}
                        rows={2}
                        placeholder="Guide the AI… e.g. make it shorter, lead with warm path, more formal tone"
                        className={cn(
                            "w-full px-3 py-2 text-[12px] font-mono leading-relaxed rounded-md resize-none",
                            "border border-border/40 bg-muted/20 text-muted-foreground",
                            "placeholder:text-muted-foreground/40",
                            "focus:outline-none focus:ring-1 focus:ring-ring/30",
                            generating && "opacity-40 cursor-not-allowed",
                        )}
                    />

                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleGenerate}
                            disabled={generating}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-all disabled:opacity-30",
                                hasTemplate
                                    ? "border border-border/60 bg-muted/40 text-foreground hover:bg-muted/70 hover:border-border"
                                    : "border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 hover:border-primary/50",
                            )}
                        >
                            {generating ? <Loader2 size={12} className="animate-spin" />
                                : hasTemplate ? <RefreshCw size={12} />
                                : <Pencil size={12} />}
                            {generating ? "Generating…" : hasTemplate ? "Regenerate" : "Generate"}
                        </button>

                        {finalScore !== null && !generating && (
                            <span className={cn(
                                "px-2 py-1 rounded-md text-[11px] font-mono font-semibold border",
                                finalScore >= 8
                                    ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/25"
                                    : finalScore >= 6
                                        ? "text-amber-400 bg-amber-500/10 border-amber-500/25"
                                        : "text-red-400 bg-red-500/10 border-red-500/25",
                            )}>
                                {finalScore}/10
                            </span>
                        )}

                        {hasTemplate && !generating && (
                            <button
                                onClick={openSendPanel}
                                disabled={showSendPanel}
                                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 transition-colors disabled:opacity-40"
                            >
                                <Send size={12} /> Approve & Send
                            </button>
                        )}
                    </div>

                    {/* Data warning */}
                    {dataWarning && (
                        <div className="flex items-start gap-2 rounded-md border border-amber-500/25 bg-amber-500/8 px-3 py-2.5">
                            <AlertTriangle size={12} className="text-amber-400 shrink-0 mt-0.5" />
                            <p className="text-[11px] font-mono text-amber-400/80 leading-relaxed">{dataWarning}</p>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
}
