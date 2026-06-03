import {
    api,
    API_BASE,
    type BatchEmailJob,
    type Campaign,
    type CampaignContact,
    type SegmentationEvent,
    type Sequence,
} from "@/shared/api/client";
import { useJobConfig } from "@/shared/hooks/useJobConfig";
import { toast } from "@/shared/lib/toast";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useLocation, useSearchParams } from "react-router-dom";
import type { OutreachContextValue } from "../context/OutreachContext";
import { PAGE_SIZE } from "../constants";
import { parseSegError } from "../utils";
import type { Tier, View } from "../types";

export function useOutreach(): OutreachContextValue & { baseId: string | null; tableId: string | null } {
    const { config: { baseId, tableId } } = useJobConfig();
    const [searchParams] = useSearchParams();
    const autoOpenedRef = useRef(false);

    // ── Navigation ────────────────────────────────────────────────────────────
    const navigate = useNavigate();
    const location = useLocation();

    // Derive current view from URL path so the browser's history stack drives navigation
    const pathSuffix = location.pathname.replace(/^\/outreach\/?/, "");
    const view: View = (["creating", "segmenting", "queue", "batch"].includes(pathSuffix)
        ? pathSuffix
        : "list") as View;

    // setView is a thin navigate wrapper — all existing call sites work unchanged
    const setView = (v: View) => navigate(v === "list" ? "/outreach" : `/outreach/${v}`);

    const [listTab, setListTab] = useState<"campaigns" | "jobs" | "sequences" | "suppressions">("campaigns");

    // ── Campaigns ─────────────────────────────────────────────────────────────
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [loading, setLoading] = useState(false);
    const [activeCampaign, setActiveCampaign] = useState<Campaign | null>(null);
    const [expandedCard, setExpandedCard] = useState<{ campaignId: number; tier: Tier | null } | null>(null);
    const [deleteTarget, setDeleteTarget] = useState<Campaign | null>(null);
    const [deleting, setDeleting] = useState(false);

    // ── Create ────────────────────────────────────────────────────────────────
    const [goal, setGoal] = useState("");
    const [creating, setCreating] = useState(false);

    // ── Batch email jobs ──────────────────────────────────────────────────────
    const [batchEmailJobs, setBatchEmailJobs] = useState<BatchEmailJob[]>([]);
    const [loadingBatchEmailJobs, setLoadingBatchEmailJobs] = useState(false);
    const [deleteBatchEmailTarget, setDeleteBatchEmailTarget] = useState<BatchEmailJob | null>(null);
    const [deletingBatchEmail, setDeletingBatchEmail] = useState<number | null>(null);

    // ── Segmentation events ───────────────────────────────────────────────────
    const [segEvents, setSegEvents] = useState<SegmentationEvent[]>([]);
    const eventsEndRef = useRef<HTMLDivElement>(null);

    // ── Queue ─────────────────────────────────────────────────────────────────
    const [queue, setQueue] = useState<CampaignContact[]>([]);
    const [queueTotal, setQueueTotal] = useState(0);
    const [hasMore, setHasMore] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const sentinelRef = useRef<HTMLDivElement>(null);
    const [queueIdx, setQueueIdx] = useState(0);
    const [actioning, setActioning] = useState(false);
    const [showSignals, setShowSignals] = useState(false);
    const [activeTier, setActiveTier] = useState<Tier>("tier_1");

    // ── Batch entry ───────────────────────────────────────────────────────────
    const [batchTier, setBatchTier] = useState<Tier>("tier_2");
    const [batchFromDeepLink, setBatchFromDeepLink] = useState(false);

    // ── Sidebar ───────────────────────────────────────────────────────────────
    const [sidebarW, setSidebarW] = useState(200);

    // ── Campaign CRUD ─────────────────────────────────────────────────────────

    const loadCampaigns = useCallback(async () => {
        if (!baseId || !tableId) return;
        setLoading(true);
        try {
            setCampaigns(await api.listCampaigns(baseId, tableId));
        } catch (e: any) {
            toast.error(e.message);
        } finally {
            setLoading(false);
        }
    }, [baseId, tableId]);

    useEffect(() => { loadCampaigns(); }, [loadCampaigns]);

    const loadBatchEmailJobs = useCallback(async () => {
        if (!baseId || !tableId) return;
        setLoadingBatchEmailJobs(true);
        try {
            setBatchEmailJobs(await api.listAllBatchEmailJobs(baseId, tableId));
        } catch (e: any) {
            toast.error(e.message);
        } finally {
            setLoadingBatchEmailJobs(false);
        }
    }, [baseId, tableId]);

    useEffect(() => {
        if (listTab === "jobs") loadBatchEmailJobs();
    }, [listTab, loadBatchEmailJobs]);

    // ── Sequences (cadence monitoring) ──────────────────────────────────────────
    const [sequences, setSequences] = useState<Sequence[]>([]);
    const [loadingSequences, setLoadingSequences] = useState(false);
    const [deleteSeqTarget, setDeleteSeqTarget] = useState<Sequence | null>(null);
    const [deletingSeq, setDeletingSeq] = useState(false);

    const loadSequences = useCallback(async () => {
        if (!baseId || !tableId) return;
        setLoadingSequences(true);
        try {
            setSequences(await api.listAllSequences(baseId, tableId));
        } catch (e: any) {
            toast.error(e.message);
        } finally {
            setLoadingSequences(false);
        }
    }, [baseId, tableId]);

    useEffect(() => {
        if (listTab !== "sequences") return;
        loadSequences();
        const t = setInterval(loadSequences, 8000); // live-ish refresh while watching
        return () => clearInterval(t);
    }, [listTab, loadSequences]);

    const toggleSequence = useCallback(async (seq: Sequence) => {
        try {
            if (seq.status === "active") await api.pauseSequence(seq.id);
            else if (seq.status === "paused") await api.resumeSequence(seq.id);
            await loadSequences();
        } catch (e: any) {
            toast.error(e.message ?? "Failed to update sequence");
        }
    }, [loadSequences]);

    const handleDeleteSequence = useCallback(async () => {
        if (!deleteSeqTarget) return;
        setDeletingSeq(true);
        try {
            await api.deleteSequence(deleteSeqTarget.id);
            setDeleteSeqTarget(null);
            await loadSequences();
        } catch (e: any) {
            toast.error(e.message ?? "Failed to delete sequence");
        } finally {
            setDeletingSeq(false);
        }
    }, [deleteSeqTarget, loadSequences]);

    // Deep-link from jobs dashboard
    useEffect(() => {
        if (autoOpenedRef.current || campaigns.length === 0) return;
        const cId = searchParams.get("campaign_id");
        const tier = searchParams.get("tier") as Tier | null;
        if (!cId || !tier) return;
        const c = campaigns.find((c) => String(c.id) === cId);
        if (!c) return;
        autoOpenedRef.current = true;
        setActiveCampaign(c);
        setBatchTier(tier);
        setBatchFromDeepLink(true);
        navigate("/outreach/batch");
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [campaigns]);

    // Segmentation SSE
    useEffect(() => {
        if (view !== "segmenting" || !activeCampaign) return;
        const es = new EventSource(`${API_BASE}/campaigns/${activeCampaign.id}/events`);
        es.onmessage = async (e) => {
            const event: SegmentationEvent = JSON.parse(e.data);
            if (event.type === "done") { es.close(); return; }
            setSegEvents((prev) => [...prev, event]);
            if (event.type === "complete") {
                es.close();
                try {
                    const updated = await api.getCampaign(activeCampaign.id);
                    setActiveCampaign(updated);
                    setExpandedCard({ campaignId: updated.id, tier: null });
                } catch {}
                setTimeout(() => { loadCampaigns(); navigate("/outreach"); }, 900);
            }
            if (event.type === "error") {
                es.close();
                toast.error(parseSegError(event.message));
                navigate("/outreach");
                loadCampaigns();
            }
        };
        es.onerror = () => es.close();
        return () => es.close();
    }, [view, activeCampaign?.id]);

    useEffect(() => {
        eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [segEvents]);

    // Infinite scroll queue
    const loadMoreQueue = useCallback(async () => {
        if (!activeCampaign || loadingMore || !hasMore) return;
        setLoadingMore(true);
        try {
            const result = await api.getCampaignQueue(activeCampaign.id, activeTier, queue.length, PAGE_SIZE);
            setQueue((prev) => [...prev, ...result.contacts]);
            setHasMore(result.has_more);
        } catch { /* silent */ } finally {
            setLoadingMore(false);
        }
    }, [activeCampaign, activeTier, loadingMore, hasMore, queue.length]);

    useEffect(() => {
        const sentinel = sentinelRef.current;
        if (!sentinel) return;
        const obs = new IntersectionObserver(
            (entries) => { if (entries[0].isIntersecting) void loadMoreQueue(); },
            { threshold: 0.1 },
        );
        obs.observe(sentinel);
        return () => obs.disconnect();
    }, [loadMoreQueue]);

    useEffect(() => {
        if (view !== "queue" || !hasMore || loadingMore || queue.length === 0) return;
        if (queueIdx < queue.length - 5) return;
        void loadMoreQueue();
    }, [queueIdx, queue.length, hasMore, loadingMore, view, loadMoreQueue]);

    // ── Handlers ──────────────────────────────────────────────────────────────

    const startDrag = (e: React.MouseEvent) => {
        const startX = e.clientX;
        const startW = sidebarW;
        const onMove = (ev: MouseEvent) =>
            setSidebarW(Math.max(160, Math.min(340, startW + ev.clientX - startX)));
        const onUp = () => {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
        e.preventDefault();
    };

    const openCampaign = (c: Campaign) => {
        if (c.status === "segmenting") {
            setActiveCampaign(c);
            setSegEvents([]);
            navigate("/outreach/segmenting");
            return;
        }
        const firstTier: Tier =
            c.tier_1_count > 0 ? "tier_1" : c.tier_2_count > 0 ? "tier_2" : "tier_3";
        enterQueue(firstTier, c);
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        setDeleting(true);
        try {
            await api.deleteCampaign(deleteTarget.id);
            setCampaigns((prev) => prev.filter((c) => c.id !== deleteTarget.id));
            setDeleteTarget(null);
            toast.success("Campaign deleted");
        } catch (err: any) {
            toast.error(err.message);
        } finally {
            setDeleting(false);
        }
    };

    const handleCreate = async (deck?: File) => {
        if (!goal.trim() || !baseId || !tableId) return;
        setCreating(true);
        try {
            const mappings = await api.listMappings(baseId, tableId);
            const mapping_id = mappings[0]?.id;
            const { campaign_id } = await api.createCampaign(baseId, tableId, goal.trim(), mapping_id);
            // Optional campaign deck — best-effort; segmentation proceeds regardless.
            if (deck) {
                try { await api.uploadCampaignDeck(campaign_id, deck); }
                catch (e: any) { toast.error(`Deck upload failed (campaign created): ${e.message}`); }
            }
            setActiveCampaign(await api.getCampaign(campaign_id));
            setSegEvents([]);
            navigate("/outreach/segmenting");
        } catch (e: any) {
            toast.error(e.message);
        } finally {
            setCreating(false);
        }
    };

    const enterBatch = (tier: Tier, campaign?: Campaign) => {
        const c = campaign ?? activeCampaign;
        if (!c) return;
        setActiveCampaign(c);
        setBatchTier(tier);
        setExpandedCard({ campaignId: c.id, tier });
        navigate("/outreach/batch");
    };

    const enterQueue = async (tier: Tier, campaign?: Campaign) => {
        const c = campaign ?? activeCampaign;
        if (!c) return;
        setActiveCampaign(c);
        setActiveTier(tier);
        setQueue([]);
        setQueueIdx(0);
        setExpandedCard({ campaignId: c.id, tier });
        setActioning(true);
        navigate("/outreach/queue");
        try {
            const result = await api.getCampaignQueue(c.id, tier, 0, PAGE_SIZE);
            setQueue(result.contacts);
            setQueueTotal(result.count);
            setHasMore(result.has_more);
            setLoadingMore(false);
        } catch (e: any) {
            toast.error(e.message);
        } finally {
            setActioning(false);
        }
    };

    const handleDeleteBatchEmail = async (job: BatchEmailJob) => {
        setDeletingBatchEmail(job.id);
        try {
            await api.deleteBatchSendJob(job.campaign_id, job.id);
            setBatchEmailJobs((prev) => prev.filter((j) => j.id !== job.id));
            setDeleteBatchEmailTarget(null);
            toast.success("Batch job removed");
        } catch (e: any) {
            toast.error(e.message);
        } finally {
            setDeletingBatchEmail(null);
        }
    };

    return {
        baseId,
        tableId,
        view, setView,
        listTab, setListTab,
        campaigns, loading, loadCampaigns,
        activeCampaign, setActiveCampaign,
        expandedCard, setExpandedCard,
        deleteTarget, setDeleteTarget,
        deleting, confirmDelete,
        openCampaign,
        goal, setGoal,
        creating, handleCreate,
        batchEmailJobs, loadingBatchEmailJobs,
        deleteBatchEmailTarget, setDeleteBatchEmailTarget,
        deletingBatchEmail, handleDeleteBatchEmail,
        sequences, loadingSequences, toggleSequence,
        deleteSeqTarget, setDeleteSeqTarget, deletingSeq, handleDeleteSequence,
        segEvents, eventsEndRef,
        queue, queueTotal, hasMore, loadingMore,
        sentinelRef, queueIdx, setQueueIdx,
        actioning, showSignals, setShowSignals,
        activeTier,
        batchTier, setBatchTier,
        batchFromDeepLink, setBatchFromDeepLink,
        enterBatch, enterQueue,
        sidebarW, startDrag,
    };
}
