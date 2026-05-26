import { api, type Batch, type Job } from "@/shared/api/client";
import { useJobConfig } from "@/shared/hooks/useJobConfig";
import { toast } from "@/shared/lib/toast";
import { useCallback, useEffect, useState } from "react";

export function useJobs() {
    const { config, updateConfig, isConfigured } = useJobConfig();
    const [draftBase,  setDraftBase]  = useState(config.baseId);
    const [draftTable, setDraftTable] = useState(config.tableId);

    const [jobs,     setJobs]     = useState<Job[]>([]);
    const [batchMap, setBatchMap] = useState<Record<number, Batch[]>>({});
    const [loading,  setLoading]  = useState(false);
    const [acting,   setActing]   = useState<number | null>(null);
    const [error,    setError]    = useState<string | null>(null);

    const [newJobOpen,       setNewJobOpen]       = useState(false);
    const [deleteJobTarget,  setDeleteJobTarget]  = useState<number | null>(null);

    const loadAll = useCallback(
        async (baseId: string, tableId: string, silent = false) => {
            if (!silent) { setLoading(true); setError(null); }
            try {
                const loaded = await api.listJobs(baseId, tableId);
                setJobs(loaded);
                await Promise.all(
                    loaded.map(async (job) => {
                        const b = await api.getBatches(job.id);
                        setBatchMap((prev) => ({ ...prev, [job.id]: b }));
                    }),
                );
            } catch (e) {
                if (!silent) setError(String(e));
            } finally {
                if (!silent) setLoading(false);
            }
        },
        [],
    );

    // Load on config change
    useEffect(() => {
        if (isConfigured) void loadAll(config.baseId, config.tableId);
    }, [config.baseId, config.tableId, isConfigured, loadAll]);

    // Auto-poll every 10s while any enrichment job is running
    useEffect(() => {
        if (!isConfigured || !jobs.some((j) => j.status === "running")) return;
        const t = setTimeout(
            () => void loadAll(config.baseId, config.tableId, true),
            10_000,
        );
        return () => clearTimeout(t);
    }, [jobs, config, isConfigured, loadAll]);

    const saveConfig = () => {
        updateConfig({ baseId: draftBase.trim(), tableId: draftTable.trim() });
    };

    const handleDelete = async (id: number) => {
        try {
            await api.deleteJob(id);
            setJobs((prev) => prev.filter((j) => j.id !== id));
            setBatchMap((prev) => { const n = { ...prev }; delete n[id]; return n; });
            toast.success(`Job #${id} deleted`);
        } catch (e) {
            toast.error(String(e));
        }
    };

    const handleAction = async (job: Job) => {
        setActing(job.id);
        try {
            if (job.status === "running") {
                await api.pauseJob(job.id);
                toast.info(`Job #${job.id} paused`);
            } else {
                await api.runJob(job.id);
                toast.success(`Job #${job.id} started`);
            }
            await loadAll(config.baseId, config.tableId);
        } catch (e) {
            toast.error(String(e));
        } finally {
            setActing(null);
        }
    };

    return {
        config, isConfigured,
        draftBase, setDraftBase,
        draftTable, setDraftTable,
        saveConfig,
        jobs, batchMap, loading, error,
        acting,
        newJobOpen, setNewJobOpen,
        deleteJobTarget, setDeleteJobTarget,
        loadAll, handleDelete, handleAction,
    };
}
