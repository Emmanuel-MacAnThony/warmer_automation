import { api, type PreflightResult } from "@/shared/api/client";
import { Button } from "@/shared/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { toast } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { BATCH_PRESETS } from "../utils";

interface NewJobSheetProps {
    open: boolean;
    onOpenChange: (o: boolean) => void;
    baseId: string;
    tableId: string;
    onCreated: () => void;
}

export function NewJobSheet({ open, onOpenChange, baseId, tableId, onCreated }: NewJobSheetProps) {
    const [viewId,           setViewId]           = useState("");
    const [linkedinUrlField, setLinkedinUrlField] = useState("LinkedIn");
    const [nameField,        setNameField]        = useState("Name");
    const [batchSize,        setBatchSize]        = useState(100);
    const [customSize,       setCustomSize]       = useState("");
    const [checking,         setChecking]         = useState(false);
    const [creating,         setCreating]         = useState(false);
    const [preflight,        setPreflight]        = useState<PreflightResult | null>(null);
    const [error,            setError]            = useState<string | null>(null);

    useEffect(() => {
        if (open) {
            setPreflight(null);
            setError(null);
            setCreating(false);
            setChecking(false);
        }
    }, [open]);

    const effectiveBatchSize = customSize ? parseInt(customSize) || 100 : batchSize;

    const handlePreflight = async () => {
        if (!viewId.trim())           { setError("Enter a View ID"); return; }
        if (!linkedinUrlField.trim()) { setError("Enter the LinkedIn URL column name"); return; }
        if (!nameField.trim())        { setError("Enter the Name column name"); return; }
        setError(null);
        setChecking(true);
        try {
            setPreflight(await api.jobPreflight(baseId, tableId, viewId.trim(), effectiveBatchSize));
        } catch (e) {
            const msg = String(e);
            setError(msg);
            toast.error(msg);
        } finally {
            setChecking(false);
        }
    };

    const handleConfirm = async () => {
        if (!preflight) return;
        setCreating(true);
        setError(null);
        try {
            const result = await api.createJob(
                baseId, tableId, viewId.trim(),
                linkedinUrlField.trim(), nameField.trim(),
                effectiveBatchSize,
            );
            toast.success(`Job #${result.job_id} created — ${result.total_batches} batches`);
            onCreated();
            onOpenChange(false);
        } catch (e) {
            const msg = String(e);
            setError(msg);
            toast.error(msg);
            setCreating(false);
        }
    };

    const inputCls = "w-full bg-background border border-border rounded-md px-3 py-2 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground";

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="sm:max-w-md flex flex-col p-0 overflow-hidden">
                <SheetHeader className="px-5 pt-5 pb-4 border-b border-border shrink-0">
                    <SheetTitle className="font-mono text-base tracking-tight">New Job</SheetTitle>
                    {baseId && tableId && (
                        <p className="text-xs text-muted-foreground font-mono">{tableId}</p>
                    )}
                </SheetHeader>

                {!preflight ? (
                    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
                        <div className="space-y-1.5">
                            <label className="text-sm text-muted-foreground font-medium">View ID</label>
                            <input
                                type="text"
                                value={viewId}
                                onChange={(e) => setViewId(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && handlePreflight()}
                                placeholder="viwXXXXXXXX"
                                className={inputCls}
                            />
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-sm text-muted-foreground font-medium">LinkedIn URL column</label>
                            <input
                                type="text"
                                value={linkedinUrlField}
                                onChange={(e) => setLinkedinUrlField(e.target.value)}
                                placeholder="LinkedIn"
                                className={inputCls}
                            />
                            <p className="text-xs text-muted-foreground">Column that holds LinkedIn profile URLs</p>
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-sm text-muted-foreground font-medium">Name column</label>
                            <input
                                type="text"
                                value={nameField}
                                onChange={(e) => setNameField(e.target.value)}
                                placeholder="Name"
                                className={inputCls}
                            />
                            <p className="text-xs text-muted-foreground">Used to search LinkedIn when URL is missing</p>
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-sm text-muted-foreground font-medium">Batch Size</label>
                            <div className="flex items-center gap-2">
                                {BATCH_PRESETS.map((size) => (
                                    <button
                                        key={size}
                                        onClick={() => { setBatchSize(size); setCustomSize(""); }}
                                        className={cn(
                                            "px-3 py-1.5 rounded-md font-mono text-sm border transition-colors",
                                            batchSize === size && !customSize
                                                ? "bg-primary text-primary-foreground border-primary"
                                                : "border-border text-muted-foreground hover:bg-muted/50",
                                        )}
                                    >
                                        {size}
                                    </button>
                                ))}
                                <input
                                    type="number"
                                    value={customSize}
                                    onChange={(e) => { setCustomSize(e.target.value); setBatchSize(0); }}
                                    placeholder="Custom"
                                    min={1} max={1000}
                                    className="w-24 bg-background border border-border rounded-md px-2 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground"
                                />
                            </div>
                        </div>

                        {error && <p className="text-sm text-red-400">{error}</p>}

                        <Button
                            size="sm"
                            onClick={handlePreflight}
                            disabled={checking || !viewId.trim() || !linkedinUrlField.trim() || !nameField.trim()}
                        >
                            {checking ? <><Loader2 size={14} className="animate-spin" /> Checking…</> : "Check Records"}
                        </Button>
                    </div>
                ) : (
                    <div className="px-4 py-4 space-y-4">
                        <div className="grid grid-cols-3 gap-3 rounded-lg border border-border bg-muted/30 p-4">
                            {[
                                { label: "Records",    value: preflight.record_count.toLocaleString() },
                                { label: "Batch Size", value: preflight.batch_size },
                                { label: "Batches",    value: preflight.batch_count },
                            ].map((s) => (
                                <div key={s.label} className="text-center">
                                    <p className="font-mono text-xs text-muted-foreground tracking-widest uppercase mb-0.5">{s.label}</p>
                                    <p className="text-2xl font-bold tabular-nums">{s.value}</p>
                                </div>
                            ))}
                        </div>

                        <div className="rounded-md border border-border/50 bg-muted/20 px-3 py-2 space-y-0.5">
                            <p className="text-xs text-muted-foreground">LinkedIn column: <span className="font-mono text-foreground">{linkedinUrlField}</span></p>
                            <p className="text-xs text-muted-foreground">Name column: <span className="font-mono text-foreground">{nameField}</span></p>
                        </div>

                        {error && <p className="text-sm text-red-400">{error}</p>}

                        <div className="flex items-center gap-2">
                            <Button variant="outline" size="sm" onClick={() => { setPreflight(null); setError(null); }}>
                                Cancel
                            </Button>
                            <Button size="sm" onClick={handleConfirm} disabled={creating}>
                                {creating ? <><Loader2 size={14} className="animate-spin" /> Creating…</> : "Confirm & Create"}
                            </Button>
                        </div>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}
