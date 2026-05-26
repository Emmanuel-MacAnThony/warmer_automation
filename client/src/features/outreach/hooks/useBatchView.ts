import { api, type BatchSendJob, type CampaignTemplate, type EmailProviderInfo, type GmailAccount, type PreviewContact, type ScopeCounts } from "@/shared/api/client";
import { ENRICHED_BLOCKLIST, FIELD_GROUPS } from "../constants";
import { withFallbacks } from "../utils";
import { toast } from "@/shared/lib/toast";
import { useEffect, useRef, useState } from "react";
import type { BatchEditorContextValue } from "../context/batch/BatchEditorContext";
import type { BatchSendContextValue } from "../context/batch/BatchSendContext";
import type { BatchStep, Tier } from "../types";
import type { Campaign } from "@/shared/api/client";

export type BatchViewHookResult = {
    editorCtx: BatchEditorContextValue;
    sendCtx: BatchSendContextValue;
    step: BatchStep;
    setStep: (s: BatchStep) => void;
};

export function useBatchView({
    campaign,
    tier,
    initialStep = "choose",
    onJobQueued,
}: {
    campaign: Campaign;
    tier: Tier;
    initialStep?: BatchStep;
    onJobQueued?: () => void;
}): BatchViewHookResult {
    // ── Step ──────────────────────────────────────────────────────────────────
    const [step, setStep] = useState<BatchStep>(initialStep);

    // ── Editor state ──────────────────────────────────────────────────────────
    const [template, setTemplate] = useState<CampaignTemplate | null>(null);
    const [subject, setSubject] = useState("");
    const [body, setBody] = useState("");
    const [dirty, setDirty] = useState(false);
    const [templateId, setTemplateId] = useState<number | null>(null);

    // ── AI generation ─────────────────────────────────────────────────────────
    const [generating, setGenerating] = useState(false);
    const [guidance, setGuidance] = useState("");
    const [guidanceHistory, setGuidanceHistory] = useState<string[]>([]);
    const [hadGuidance, setHadGuidance] = useState(false);
    const [dataWarning, setDataWarning] = useState("");
    const [thinking, setThinking] = useState("");
    const [thinkDone, setThinkDone] = useState(false);
    const [critiqueText, setCritiqueText] = useState("");
    const [critiqueDone, setCritiqueDone] = useState(false);
    const [critiqueScore, setCritiqueScore] = useState<number | null>(null);
    const [rewriteText, setRewriteText] = useState("");
    const [rewriteDone, setRewriteDone] = useState(false);
    const [finalScore, setFinalScore] = useState<number | null>(null);
    const [subjectVariants, setSubjectVariants] = useState<string[]>([]);
    const thinkRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    // ── File upload ───────────────────────────────────────────────────────────
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [uploadingFile, setUploadingFile] = useState(false);
    const [dragOver, setDragOver] = useState(false);

    // ── Variables / preview ───────────────────────────────────────────────────
    const [airtableFields, setAirtableFields] = useState<string[]>([]);
    const [enrichedFields, setEnrichedFields] = useState<string[]>([]);
    const [varPopover, setVarPopover] = useState<string | null>(null);
    const [fallbackInput, setFallbackInput] = useState("");
    const [showPreview, setShowPreview] = useState(false);
    const [previews, setPreviews] = useState<PreviewContact[]>([]);
    const [previewIdx, setPreviewIdx] = useState(0);
    const [loadingPrev, setLoadingPrev] = useState(false);

    // ── Sender accounts ───────────────────────────────────────────────────────
    const [accounts, setAccounts] = useState<GmailAccount[]>([]);
    const [loadingAccounts, setLoadingAccounts] = useState(false);
    const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
    const [testMode, setTestMode] = useState(false);
    // Active outbound provider — gmail uses per-account selection; smtp/resend
    // are server-configured single senders (no account picker needed).
    const [emailProvider, setEmailProvider] = useState<EmailProviderInfo>({
        provider: "gmail", from_email: null, requires_account: true,
    });

    // ── Send panel ────────────────────────────────────────────────────────────
    const [showSendPanel, setShowSendPanel] = useState(false);
    const [scopeCounts, setScopeCounts] = useState<ScopeCounts | null>(null);
    const [loadingScopes, setLoadingScopes] = useState(false);
    const [queueingJob, setQueueingJob] = useState(false);

    // ── Sequence (cadence) builder ──────────────────────────────────────────────
    const [sendMode, setSendMode] = useState<"single" | "sequence">("single");
    const [seqSteps, setSeqSteps] = useState<{ template_id: number; subject: string; body: string; delay_days: number }[]>([]);
    const [addingStep, setAddingStep] = useState(false);
    const [launchingSeq, setLaunchingSeq] = useState(false);

    // ── Job ───────────────────────────────────────────────────────────────────
    const [activeJob, setActiveJob] = useState<BatchSendJob | null>(null);
    const [confirmCancelJob, setConfirmCancelJob] = useState(false);
    const [currentContact, setCurrentContact] = useState("");
    const [pauseReason, setPauseReason] = useState<string | null>(null);

    // ── Template drawer ───────────────────────────────────────────────────────
    const [showTplDrawer, setShowTplDrawer] = useState(false);
    const [drawerTemplate, setDrawerTemplate] = useState<CampaignTemplate | null>(null);

    // ── Computed ──────────────────────────────────────────────────────────────
    const hasTemplate = !!template || subject !== "" || body !== "";
    const approved = template?.status === "approved";
    const curPreview = previews[previewIdx] ?? null;
    const jobIsActive = !!activeJob && (activeJob.status === "pending" || activeJob.status === "running");

    // ── Effects ───────────────────────────────────────────────────────────────

    // Load saved template only in details view — choose flow is always fresh
    useEffect(() => {
        if (initialStep === "choose") return;
        api.getCampaignTemplate(campaign.id, tier)
            .then((t) => { setTemplate(t); setSubject(t.subject); setBody(t.body); setTemplateId(t.id); })
            .catch(() => {});
    }, [campaign.id, tier]);

    // Fetch Airtable schema fields
    useEffect(() => {
        api.getSchema(campaign.base_id, campaign.table_id)
            .then((r) => setAirtableFields(r.fields.map((f) => f.name)))
            .catch(() => {});
    }, [campaign.base_id, campaign.table_id]);

    // Derive enriched fields from field_mapping — only the LLM-extracted Airtable columns
    // (e.g. "Realtime role", "Realtime company name"). Excludes identity/contact fields
    // the user owns (Name, Email, LinkedIn URL, etc.) and internal artifacts.
    useEffect(() => {
        api.listMappings(campaign.base_id, campaign.table_id)
            .then((mappings) => {
                if (!mappings.length) return;
                const known = new Set(Object.values(FIELD_GROUPS).flat());
                // Canonical keys that belong to the user's CRM identity data,
                // not to data our LLM extracts from LinkedIn.
                const identityKeys = new Set([
                    "linkedin_url", "full_name", "first_name", "last_name",
                    "email", "phone", "twitter", "website", "profile_image",
                    "linkedin_id", "linkedin_urn",
                    "enriched_at", "enrichment_source",
                    "is_premium", "is_open_to_work", "is_creator",
                    "recommendations_received",
                    "similar_profiles", "similar_profiles_count",
                    "experiences", "educations", "certifications", "publications",
                ]);
                const seen = new Set<string>();
                const fields: string[] = [];
                for (const mapping of mappings) {
                    for (const cfg of Object.values(mapping.mappings)) {
                        const name = cfg.airtable_name;
                        const ck = cfg.canonical_key;
                        if (!name || seen.has(name)) continue;
                        if (known.has(name)) continue;
                        if (ENRICHED_BLOCKLIST.has(name)) continue;
                        if (name.startsWith("tweet_")) continue;
                        if (identityKeys.has(ck)) continue;
                        seen.add(name);
                        fields.push(name);
                    }
                }
                setEnrichedFields(fields);
            })
            .catch(() => {});
    }, [campaign.base_id, campaign.table_id]);

    // Debounced preview refresh
    useEffect(() => {
        // Strip HTML tags to check for real text content
        const hasContent = subject.trim() || body.replace(/<[^>]*>/g, "").trim();
        if (!hasContent) {
            setLoadingPrev(false);
            setPreviews([]);
            return;
        }
        setLoadingPrev(true); // show spinner immediately, before the debounce fires
        const t = setTimeout(() => {
            api.previewCampaignTemplate(campaign.id, tier, subject, body)
                .then((ps) => { setPreviews(ps); setPreviewIdx(0); })
                .catch((e: any) => {
                    setPreviews([]);
                    toast.error(e?.message ?? "Preview failed");
                })
                .finally(() => setLoadingPrev(false));
        }, 800);
        return () => clearTimeout(t);
    }, [subject, body, campaign.id, tier]);

    // Load latest batch job on mount; restore rate-limit banner if job is paused with retry_after
    useEffect(() => {
        api.listBatchSendJobs(campaign.id, tier)
            .then((jobs) => {
                if (!jobs[0]) return;
                setActiveJob(jobs[0]);
                const job = jobs[0];
                if (job.status === "paused" && job.retry_after) {
                    const retryDate = new Date(job.retry_after);
                    const retryMsg = retryDate > new Date()
                        ? `Gmail rate limit hit — try again after ${retryDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`
                        : "Gmail sending limit reached — this may be a daily quota. Try again tomorrow or use a different account.";
                    setPauseReason(retryMsg);
                }
            })
            .catch(() => {});
    }, [campaign.id, tier]);

    // In details view, load the job-specific template (not just latest)
    useEffect(() => {
        if (step !== "details") return;
        if (!activeJob?.template_id) return;
        if (template?.id === activeJob.template_id) return;
        api.getTemplateById(campaign.id, activeJob.template_id)
            .then((t) => setTemplate(t))
            .catch(() => {});
    }, [step, activeJob?.template_id, template?.id, campaign.id]);

    // SSE subscription for real-time job progress
    // Subscribes when the job is active (running/pending), reconnects on resume.
    // The backend sends a synthetic final event for already-finished jobs so we
    // always get the authoritative final state on mount even if we missed the run.
    useEffect(() => {
        if (!activeJob || !jobIsActive) {
            setCurrentContact("");
            return;
        }
        const url = `/api/campaigns/${campaign.id}/batch-jobs/${activeJob.id}/events`;
        const source = new EventSource(url);

        source.onmessage = (e) => {
            try {
                const evt = JSON.parse(e.data);
                if (evt.type === "start") {
                    setActiveJob((j) => j ? { ...j, status: "running", sent: evt.sent, failed: evt.failed, total: evt.total } : null);
                } else if (evt.type === "progress") {
                    setActiveJob((j) => j ? { ...j, sent: evt.sent, failed: evt.failed, total: evt.total } : null);
                    if (evt.current) setCurrentContact(evt.current);
                } else if (evt.type === "complete") {
                    setActiveJob((j) => j ? { ...j, status: "completed", sent: evt.sent, failed: evt.failed } : null);
                    setCurrentContact("");
                    source.close();
                } else if (evt.type === "paused") {
                    setActiveJob((j) => j ? { ...j, status: "paused", sent: evt.sent, failed: evt.failed } : null);
                    if (evt.reason === "rate_limited") {
                        const retryMsg = evt.retry_at
                            ? `Gmail rate limit hit — try again after ${new Date(evt.retry_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`
                            : "Gmail sending limit reached — this may be a daily quota. Try again tomorrow or use a different account.";
                        setPauseReason(retryMsg);
                    }
                    setCurrentContact("");
                    source.close();
                } else if (evt.type === "cancelled") {
                    setActiveJob((j) => j ? { ...j, status: "cancelled", sent: evt.sent, failed: evt.failed } : null);
                    setCurrentContact("");
                    source.close();
                } else if (evt.type === "error") {
                    setActiveJob((j) => j ? { ...j, status: "failed" } : null);
                    setCurrentContact("");
                    source.close();
                }
            } catch { /* malformed event — ignore */ }
        };

        source.onerror = () => source.close();

        return () => source.close();
    }, [activeJob?.id, activeJob?.status, campaign.id]);

    // Poll job status every 3s as a stats-refresh fallback (SSE handles the live ticker).
    // Runs for any non-terminal job so the sent/failed counts are always fresh.
    useEffect(() => {
        if (!activeJob) return;
        if (["completed", "failed", "cancelled"].includes(activeJob.status)) return;
        const t = setInterval(() => {
            api.listBatchSendJobs(campaign.id, tier)
                .then((jobs) => {
                    const fresh = jobs.find((j) => j.id === activeJob.id);
                    if (fresh) setActiveJob(fresh);
                })
                .catch(() => {});
        }, 3000);
        return () => clearInterval(t);
    }, [activeJob?.id, activeJob?.status, campaign.id, tier]);

    // Load sender accounts on mount — auto-select all connected
    useEffect(() => {
        setLoadingAccounts(true);
        api.listGmailAccounts()
            .then((accounts) => {
                setAccounts(accounts);
                setSelectedAccounts(accounts.map((a) => a.email));
            })
            .catch(() => {})
            .finally(() => setLoadingAccounts(false));
    }, []);

    // Detect the active email provider so the send panel renders the right UI
    useEffect(() => {
        api.getEmailProvider().then(setEmailProvider).catch(() => {});
    }, []);

    // Auto-scroll thinking panel
    useEffect(() => {
        if (thinkRef.current)
            thinkRef.current.scrollTop = thinkRef.current.scrollHeight;
    }, [thinking]);

    // ── Handlers ──────────────────────────────────────────────────────────────

    const toggleAccount = (email: string) => {
        setSelectedAccounts((prev) =>
            prev.includes(email) ? prev.filter((e) => e !== email) : [...prev, email],
        );
    };

    const handleConnectAccount = () => {
        const popup = window.open("/api/auth/gmail", "gmail-oauth", "width=520,height=620,scrollbars=yes,resizable=yes");
        const onMessage = (e: MessageEvent) => {
            if (e.data?.type !== "gmail-oauth") return;
            window.removeEventListener("message", onMessage);
            popup?.close();
            if (e.data.success) {
                const email = e.data.email as string;
                api.listGmailAccounts()
                    .then((accounts) => {
                        setAccounts(accounts);
                        setSelectedAccounts((prev) => prev.includes(email) ? prev : [...prev, email]);
                    })
                    .catch(() => {});
                toast.success(`Connected ${email}`);
            } else {
                toast.error(`Gmail connection failed: ${e.data.error ?? "unknown error"}`);
            }
        };
        window.addEventListener("message", onMessage);
    };

    const handleDisconnectAccount = async (email: string) => {
        await api.disconnectGmail(email).catch(() => {});
        setAccounts((prev) => prev.filter((a) => a.email !== email));
        setSelectedAccounts((prev) => prev.filter((e) => e !== email));
        toast.success(`${email} disconnected`);
    };

    const openSendPanel = async () => {
        setShowSendPanel(true);
        setLoadingScopes(true);
        try {
            setScopeCounts(await api.getScopeCounts(campaign.id, tier));
        } catch {
            toast.error("Failed to load scope counts");
        } finally {
            setLoadingScopes(false);
        }
    };

    const handleQueueJob = async () => {
        setQueueingJob(true);
        try {
            let tid = templateId;
            if (dirty || !tid) {
                const vars = [
                    ...new Set([
                        ...[...subject.matchAll(/\[(\w+)/g)].map((m) => m[1]),
                        ...[...body.matchAll(/\[(\w+)/g)].map((m) => m[1]),
                    ]),
                ];
                const saved = await api.saveCampaignTemplate(campaign.id, tier, {
                    subject, body, variables: vars, template_id: tid ?? undefined,
                });
                setTemplate(saved);
                setTemplateId(saved.id);
                setDirty(false);
                tid = saved.id;
            }
            const scope = testMode ? "everyone" : (scopeCounts && scopeCounts.unsent > 0 ? "unsent" : "everyone");
            const job = await api.createBatchSendJob(
                campaign.id, tier, scope, tid ?? undefined,
                selectedAccounts,
                testMode ? "macanthonyemmanuel9@gmail.com" : undefined,
            );
            setActiveJob(job);
            setShowSendPanel(false);
            setStep("details");
            onJobQueued?.();
            toast.success(`Job queued — ${job.total} contacts`);
        } catch (e: any) {
            toast.error(e.message ?? "Failed to queue job");
        } finally {
            setQueueingJob(false);
        }
    };

    // Ensure the current editor content is saved as a template; returns its id.
    const ensureTemplateSaved = async (): Promise<number | null> => {
        let tid = templateId;
        if (dirty || !tid) {
            const vars = [
                ...new Set([
                    ...[...subject.matchAll(/\[(\w+)/g)].map((m) => m[1]),
                    ...[...body.matchAll(/\[(\w+)/g)].map((m) => m[1]),
                ]),
            ];
            const saved = await api.saveCampaignTemplate(campaign.id, tier, {
                subject, body, variables: vars, template_id: tid ?? undefined,
            });
            setTemplate(saved);
            setTemplateId(saved.id);
            setDirty(false);
            tid = saved.id;
        }
        return tid ?? null;
    };

    // Generate one follow-up email (a fresh template). Returns id + subject + body.
    const generateFollowUp = async (followUpNumber: number): Promise<{ id: number; subject: string; body: string } | null> => {
        const res = await fetch(`/api/campaigns/${campaign.id}/templates/${tier}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                guidance: `This is follow-up #${followUpNumber} in an email sequence. Keep it short (2-3 sentences). Warmly reference that you reached out before without repeating the first email, and gently restate the ask.`,
                current_subject: "", current_body: "",
                guidance_history: guidanceHistory,
                airtable_fields: airtableFields,
            }),
        });
        if (!res.ok || !res.body) return null;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        let tpl: CampaignTemplate | null = null;
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const parts = buf.split("\n\n");
            buf = parts.pop()!;
            for (const part of parts) {
                if (!part.startsWith("data: ")) continue;
                const evt = JSON.parse(part.slice(6));
                if (evt.type === "complete") tpl = evt.template as CampaignTemplate;
            }
        }
        return tpl ? { id: tpl.id, subject: tpl.subject, body: tpl.body } : null;
    };

    const addFollowUp = async (delay_days: number) => {
        setAddingStep(true);
        try {
            const t = await generateFollowUp(seqSteps.length + 1);
            if (t) setSeqSteps((s) => [...s, { template_id: t.id, subject: t.subject, body: t.body, delay_days }]);
            else toast.error("Could not generate follow-up");
        } catch (e: any) {
            toast.error(e.message ?? "Follow-up generation failed");
        } finally {
            setAddingStep(false);
        }
    };

    const updateSeqStep = (idx: number, patch: Partial<{ subject: string; body: string }>) =>
        setSeqSteps((s) => s.map((st, i) => (i === idx ? { ...st, ...patch } : st)));

    const removeSeqStep = (idx: number) => setSeqSteps((s) => s.filter((_, i) => i !== idx));
    const setSeqStepDelay = (idx: number, days: number) =>
        setSeqSteps((s) => s.map((st, i) => (i === idx ? { ...st, delay_days: Math.max(1, days) } : st)));

    const handleLaunchSequence = async () => {
        setLaunchingSeq(true);
        try {
            const step1 = await ensureTemplateSaved();
            if (!step1) { toast.error("Generate the first email first"); return; }
            // Persist any hand-edits to each follow-up's template before launching.
            for (const s of seqSteps) {
                const vars = [
                    ...new Set([
                        ...[...s.subject.matchAll(/\[(\w+)/g)].map((m) => m[1]),
                        ...[...s.body.matchAll(/\[(\w+)/g)].map((m) => m[1]),
                    ]),
                ];
                await api.saveCampaignTemplate(campaign.id, tier, {
                    subject: s.subject, body: s.body, variables: vars, template_id: s.template_id,
                });
            }
            const steps = [
                { delay_days: 0, template_id: step1 },
                ...seqSteps.map((s) => ({ delay_days: s.delay_days, template_id: s.template_id })),
            ];
            const { id } = await api.createSequence(campaign.id, {
                tier, name: "Sequence", steps,
                sender_emails: selectedAccounts,
                test_recipient: testMode ? "macanthonyemmanuel9@gmail.com" : undefined,
            });
            const { enrolled } = await api.launchSequence(id);
            toast.success(`Sequence launched — ${enrolled.toLocaleString()} contacts enrolled`);
            setShowSendPanel(false);
            setSendMode("single");
            setSeqSteps([]);
            onJobQueued?.();
        } catch (e: any) {
            toast.error(e.message ?? "Failed to launch sequence");
        } finally {
            setLaunchingSeq(false);
        }
    };

    const handleGenerate = async () => {
        const currentGuidance = guidance.trim();
        setHadGuidance(!!currentGuidance);
        if (currentGuidance) {
            setGuidanceHistory((prev) => [...prev.slice(-4), currentGuidance]);
        }
        abortRef.current = new AbortController();
        setGenerating(true);
        setThinking("");
        setThinkDone(false);
        setCritiqueText("");
        setCritiqueDone(false);
        setCritiqueScore(null);
        setRewriteText("");
        setRewriteDone(false);
        setFinalScore(null);
        setDataWarning("");
        setSubjectVariants([]);
        try {
            const res = await fetch(
                `/api/campaigns/${campaign.id}/templates/${tier}/generate`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        guidance: currentGuidance,
                        current_subject: subject,
                        current_body: body,
                        template_id: templateId ?? undefined,
                        guidance_history: guidanceHistory,
                        airtable_fields: airtableFields,
                    }),
                    signal: abortRef.current.signal,
                },
            );
            if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const parts = buf.split("\n\n");
                buf = parts.pop()!;
                for (const part of parts) {
                    if (!part.startsWith("data: ")) continue;
                    const evt = JSON.parse(part.slice(6));
                    if (evt.type === "data_warning") {
                        setDataWarning(evt.text);
                    } else if (evt.type === "status") {
                        // Single clean status line: "Reading…" → "Writing…" → "Polishing…" → "Done"
                        setThinking(evt.label ?? "");
                        setThinkDone(evt.step === "done");
                    } else if (evt.type === "draft") {
                        // Email streams live into the editor fields as it's written
                        if (typeof evt.subject === "string") setSubject(evt.subject);
                        if (typeof evt.body === "string") setBody(evt.body);
                    } else if (evt.type === "subject_variants") {
                        setSubjectVariants(evt.variants ?? []);
                    } else if (evt.type === "complete") {
                        const t = evt.template as CampaignTemplate;
                        setTemplate(t);
                        setSubject(withFallbacks(t.subject));
                        setBody(withFallbacks(t.body));
                        setTemplateId(t.id);
                        setDirty(false);
                        if (evt.score != null) setFinalScore(evt.score as number);
                    } else if (evt.type === "error") {
                        toast.error(evt.message ?? "Generation failed");
                    }
                }
            }
        } catch (e: any) {
            if (e?.name !== "AbortError") toast.error(e.message ?? "Generation failed");
        } finally {
            setGenerating(false);
        }
    };

    const handleCancel = () => {
        abortRef.current?.abort();
        setGenerating(false);
    };

    const handlePauseJob = async () => {
        if (!activeJob) return;
        try {
            await api.pauseBatchSendJob(campaign.id, activeJob.id);
            setActiveJob((j) => j ? { ...j, status: "paused" } : null);
        } catch (e: any) {
            toast.error(e.message ?? "Failed to pause");
        }
    };

    const handleResumeJob = async () => {
        if (!activeJob) return;
        try {
            await api.resumeBatchSendJob(campaign.id, activeJob.id);
            setActiveJob((j) => j ? { ...j, status: "running" } : null);
            setPauseReason(null);
        } catch (e: any) {
            toast.error(e.message ?? "Failed to resume");
        }
    };

    const handleCancelActiveJob = async () => {
        if (!activeJob) return;
        try {
            await api.cancelBatchSendJob(campaign.id, activeJob.id);
            setActiveJob(null);
            setConfirmCancelJob(false);
            toast.success("Job cancelled");
        } catch (e: any) {
            setConfirmCancelJob(false);
            toast.error(e.message ?? "Failed to cancel");
        }
    };

    const mapVariable = (from: string, to: string) => {
        const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const re = new RegExp(`\\[${escaped}(?:\\s*\\|[^\\]]*)?\\]`, "g");
        const replacement = withFallbacks(`[${to}]`);
        setSubject((s) => s.replace(re, replacement));
        setBody((b) => b.replace(re, replacement));
        setDirty(true);
        setVarPopover(null);
    };

    const applyFallback = (varName: string, fallback: string) => {
        const escaped = varName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const re = new RegExp(`\\[${escaped}(?:\\s*\\|[^\\]]*)?\\]`, "g");
        const replacement = fallback.trim()
            ? `[${varName} | fallback: "${fallback.trim()}"]`
            : `[${varName}]`;
        setSubject((s) => s.replace(re, replacement));
        setBody((b) => b.replace(re, replacement));
        setDirty(true);
        setVarPopover(null);
        setFallbackInput("");
    };

    const handleFileUpload = async (file: File) => {
        if (!file) return;
        setUploadingFile(true);
        try {
            const result = await api.parseTemplateFile(campaign.id, file);
            setBody(withFallbacks(result.text));
            setSubject("");
            setDirty(true);
            setStep("editor");
        } catch (e: any) {
            toast.error(e.message ?? "Failed to parse file");
        } finally {
            setUploadingFile(false);
        }
    };

    // ── Return shaped context values ──────────────────────────────────────────

    const editorCtx: BatchEditorContextValue = {
        template, setTemplate,
        subject, setSubject,
        body, setBody,
        dirty, setDirty,
        templateId, setTemplateId,
        hasTemplate, approved,
        generating,
        guidance, setGuidance,
        guidanceHistory, hadGuidance,
        dataWarning,
        thinking, setThinking,
        thinkDone, setThinkDone,
        critiqueText, setCritiqueText, critiqueDone, setCritiqueDone, critiqueScore, setCritiqueScore,
        rewriteText, setRewriteText, rewriteDone, setRewriteDone,
        finalScore,
        subjectVariants, setSubjectVariants,
        thinkRef,
        handleGenerate, handleCancel,
        fileInputRef,
        uploadingFile, dragOver, setDragOver,
        handleFileUpload,
        airtableFields,
        enrichedFields,
        varPopover, setVarPopover,
        fallbackInput, setFallbackInput,
        mapVariable, applyFallback,
        showPreview, setShowPreview,
        previews, previewIdx, setPreviewIdx,
        loadingPrev, curPreview,
    };

    const sendCtx: BatchSendContextValue = {
        accounts, loadingAccounts, selectedAccounts,
        toggleAccount, handleConnectAccount, handleDisconnectAccount,
        emailProvider,
        testMode, setTestMode,
        showSendPanel, setShowSendPanel, openSendPanel,
        scopeCounts, loadingScopes,
        queueingJob, handleQueueJob,
        sendMode, setSendMode,
        seqSteps, addingStep, launchingSeq,
        addFollowUp, updateSeqStep, removeSeqStep, setSeqStepDelay, handleLaunchSequence,
        activeJob, jobIsActive, currentContact,
        pauseReason, setPauseReason,
        confirmCancelJob, setConfirmCancelJob,
        handlePauseJob, handleResumeJob, handleCancelActiveJob,
        showTplDrawer, setShowTplDrawer,
        drawerTemplate, setDrawerTemplate,
    };

    return { editorCtx, sendCtx, step, setStep };
}
