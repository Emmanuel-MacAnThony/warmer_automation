import { api, type Suppression } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { ConfirmDialog } from "@/shared/components/ui/dialog";
import { cn } from "@/shared/lib/utils";
import { Ban, Loader2, Search, UndoDot } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/shared/lib/toast";

function fmtDate(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(undefined, {
        day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
    });
}

const REASON_STYLE: Record<Suppression["reason"], string> = {
    hard_bounce:   "text-red-400 bg-red-500/10 border-red-500/25",
    soft_bounce:   "text-amber-400 bg-amber-500/10 border-amber-500/25",
    mx_invalid:    "text-red-400/80 bg-red-500/5 border-red-500/20",
    sync_rejected: "text-red-400 bg-red-500/10 border-red-500/25",
    unsubscribed:  "text-muted-foreground bg-muted/40 border-border/40",
    manual:        "text-muted-foreground bg-muted/40 border-border/40",
};

const REASON_LABEL: Record<Suppression["reason"], string> = {
    hard_bounce:   "Hard bounce",
    soft_bounce:   "Soft bounce",
    mx_invalid:    "Domain dead (MX)",
    sync_rejected: "Gmail rejected",
    unsubscribed:  "Unsubscribed",
    manual:        "Manual",
};

export function SuppressionsView() {
    const [rows, setRows] = useState<Suppression[]>([]);
    const [activeCount, setActiveCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState("");
    const [confirmTarget, setConfirmTarget] = useState<Suppression | null>(null);
    const [unsuppressing, setUnsuppressing] = useState(false);

    const load = async (q: string) => {
        setLoading(true);
        try {
            const res = await api.listSuppressions({ search: q || undefined, limit: 200 });
            setRows(res.suppressions);
            setActiveCount(res.active_count);
        } catch (e: any) {
            toast.error(e?.message ?? "Failed to load suppressions");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load("");
    }, []);

    // Debounced search.
    useEffect(() => {
        const t = setTimeout(() => load(search), 250);
        return () => clearTimeout(t);
    }, [search]);

    const handleUnsuppress = async () => {
        if (!confirmTarget) return;
        setUnsuppressing(true);
        try {
            await api.unsuppress(confirmTarget.email);
            toast.success(`Removed ${confirmTarget.email} from suppressions`);
            setRows(prev => prev.filter(r => r.email !== confirmTarget.email));
            setActiveCount(c => Math.max(0, c - 1));
            setConfirmTarget(null);
        } catch (e: any) {
            toast.error(e?.message ?? "Failed to unsuppress");
        } finally {
            setUnsuppressing(false);
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3">
                <Ban size={16} className="text-red-400/70" />
                <h2 className="text-sm font-mono uppercase tracking-widest text-muted-foreground/60">
                    Suppression list <span className="text-foreground/70">· {activeCount} active</span>
                </h2>
            </div>

            <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/40" />
                <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Filter by email or domain"
                    className="w-full pl-9 pr-3 py-2 rounded-md border border-border/50 bg-background text-sm font-mono focus:outline-none focus:border-border"
                />
            </div>

            {loading && rows.length === 0 ? (
                <div className="flex items-center gap-2 text-[12px] text-muted-foreground py-8 justify-center">
                    <Loader2 size={13} className="animate-spin" /> Loading…
                </div>
            ) : rows.length === 0 ? (
                <Card className="px-6 py-10 text-center text-[12px] text-muted-foreground/60">
                    {search ? "No matching suppressions." : "No suppressions yet — your sending domain is clean."}
                </Card>
            ) : (
                <Card className="overflow-hidden">
                    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2 border-b border-border/40 text-[9px] font-mono uppercase tracking-widest text-muted-foreground/45">
                        <span>Email</span>
                        <span>Reason</span>
                        <span>Last status</span>
                        <span>Last seen</span>
                        <span></span>
                    </div>
                    <div className="divide-y divide-border/30">
                        {rows.map((r) => (
                            <div key={r.id} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 items-center px-4 py-2.5">
                                <span className="truncate font-mono text-[12px] text-foreground/85" title={r.last_reason_text ?? undefined}>
                                    {r.email}
                                </span>
                                <span className={cn("text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-wide shrink-0", REASON_STYLE[r.reason])}>
                                    {REASON_LABEL[r.reason]}
                                </span>
                                <span className="font-mono text-[10px] text-muted-foreground/70 shrink-0 min-w-12 text-center">
                                    {r.last_smtp_status ?? "—"}
                                </span>
                                <span className="text-[11px] text-muted-foreground/60 shrink-0">
                                    {fmtDate(r.last_seen_at)}
                                </span>
                                <button
                                    onClick={() => setConfirmTarget(r)}
                                    className="h-6 px-2 rounded text-[10px] font-mono text-muted-foreground/50 hover:text-foreground hover:bg-muted transition-colors shrink-0 flex items-center gap-1"
                                    title="Remove from suppression list (allow future sends)"
                                >
                                    <UndoDot size={11} /> Unsuppress
                                </button>
                            </div>
                        ))}
                    </div>
                </Card>
            )}

            <ConfirmDialog
                open={confirmTarget !== null}
                onOpenChange={(o) => { if (!o) setConfirmTarget(null); }}
                title="Remove from suppressions?"
                description={
                    confirmTarget
                        ? `This will allow future sequences and batch jobs to email ${confirmTarget.email} again. If the original bounce reason still applies, this address will likely bounce again.`
                        : ""
                }
                confirmLabel={unsuppressing ? "Removing…" : "Unsuppress"}
                onConfirm={handleUnsuppress}
                loading={unsuppressing}
            />
        </div>
    );
}
