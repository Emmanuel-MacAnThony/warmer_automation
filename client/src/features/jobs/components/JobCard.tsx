import { type Batch, type Job, api } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { StatusBadge } from "@/shared/components/ui/status-badge";
import { toast } from "@/shared/lib/toast";
import { motion } from "framer-motion";
import { AlertTriangle, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { agg } from "../utils";
import { JobPipeline } from "./JobPipeline";

interface JobCardProps {
    job: Job;
    batches: Batch[];
    acting: boolean;
    onAction: (job: Job) => void;
    onDelete: (id: number) => void;
    onRefresh: () => void;
}

export function JobCard({ job, batches, acting, onAction, onDelete, onRefresh }: JobCardProps) {
    const [rerunning, setRerunning] = useState(false);
    const [pauseBannerDismissed, setPauseBannerDismissed] = useState(false);

    useEffect(() => {
        if (job.status !== "paused") setPauseBannerDismissed(false);
    }, [job.status]);

    const stats = agg(batches);
    const total = job.total_records ?? 0;
    const pct   = total > 0 ? Math.min(100, Math.round((stats.processed / total) * 100)) : 0;
    const canAct = job.status === "running" || job.status === "pending" || job.status === "paused";

    const handleRerun = async () => {
        setRerunning(true);
        try {
            await api.rerunJob(job.id);
            toast.info(`Job #${job.id} reset — click Run to start enrichment again`);
            onRefresh();
        } catch (e: any) {
            toast.error(e.message ?? String(e));
        } finally {
            setRerunning(false);
        }
    };

    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
            <Card className="overflow-hidden w-full rounded-md border-border/70">
                <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/50">
                    <span className="font-mono text-xs text-muted-foreground/50 shrink-0">#{job.id}</span>
                    <StatusBadge status={job.status} />
                    <span className="text-sm text-muted-foreground/70 font-mono">
                        {total > 0 ? total.toLocaleString() : "?"} records
                        {job.total_batches != null && <span className="text-muted-foreground/40"> · {job.total_batches} batches</span>}
                    </span>
                    <span className="ml-auto text-[11px] font-mono text-muted-foreground/40 shrink-0">
                        {new Date(job.created_at).toLocaleDateString()}
                    </span>
                    <button
                        onClick={() => onDelete(job.id)}
                        className="p-1 rounded hover:bg-red-500/10 hover:text-red-400 text-muted-foreground/20 transition-colors shrink-0"
                    >
                        <Trash2 size={12} />
                    </button>
                </div>

                {job.status === "paused" && job.pause_reason === "rate_limited" && !pauseBannerDismissed && (
                    <div className="flex items-start gap-3 px-4 py-3 border-b border-amber-500/20 bg-amber-500/5">
                        <AlertTriangle size={13} className="text-amber-400 shrink-0 mt-0.5" />
                        <p className="flex-1 text-[11px] font-mono text-amber-300/80 leading-relaxed">
                            Job auto-paused — Apify hit a rate limit. Wait a few minutes then resume.
                        </p>
                        <button
                            onClick={() => setPauseBannerDismissed(true)}
                            className="text-amber-400/40 hover:text-amber-400 transition-colors shrink-0"
                        >
                            <X size={12} />
                        </button>
                    </div>
                )}
                <JobPipeline
                    jobId={job.id}
                    jobStatus={job.status}
                    batches={batches}
                    stats={stats}
                    total={total}
                    pct={pct}
                    onAction={() => onAction(job)}
                    acting={acting}
                    canAct={canAct}
                    onRerun={handleRerun}
                    rerunning={rerunning}
                />
            </Card>
        </motion.div>
    );
}
