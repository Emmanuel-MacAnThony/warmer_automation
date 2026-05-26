import type { Batch } from "@/shared/api/client";
import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { batchDot } from "../utils";

export function BatchRow({ b }: { b: Batch }) {
    const [open, setOpen] = useState(false);

    const pct  = b.total > 0 ? Math.min(100, Math.round((b.processed / b.total) * 100)) : 0;
    const hpct = b.processed > 0 ? Math.round(((b.hits   ?? 0) / b.processed) * 100) : 0;
    const mpct = b.processed > 0 ? Math.round(((b.misses ?? 0) / b.processed) * 100) : 0;
    const done = b.status === "completed" || b.status === "failed";

    const statCells: { label: string; value: number | string; sub: string; color: string }[] = [
        { label: "Processed", value: b.processed,   sub: `of ${b.total}`, color: "text-foreground" },
        { label: "Hits",      value: b.hits   ?? 0, sub: `${hpct}%`,      color: "text-primary/70" },
        { label: "Misses",    value: b.misses ?? 0, sub: `${mpct}%`,      color: "text-muted-foreground" },
        {
            label: "Errors",
            value: b.failed ?? 0,
            sub: "",
            color: (b.failed ?? 0) > 0 ? "text-red-400" : "text-muted-foreground",
        },
        { label: "Progress",  value: `${pct}%`,     sub: `${b.processed}/${b.total}`, color: "text-primary" },
    ];

    return (
        <div className="border-t border-border/40">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center gap-2.5 px-4 py-3 hover:bg-muted/40 transition-colors text-left"
            >
                <ChevronRight
                    size={14}
                    className={cn("text-muted-foreground transition-transform duration-150 shrink-0", open && "rotate-90")}
                />
                <span className="font-mono text-sm text-muted-foreground w-8 shrink-0">B{b.batch_number}</span>
                <span className={cn("w-2.5 h-2.5 rounded-full shrink-0", batchDot[b.status] ?? "bg-muted-foreground")} />
                <span className="text-base text-muted-foreground">{b.total} records</span>

                <span className="ml-auto flex items-center gap-3 text-sm shrink-0">
                    {done ? (
                        <>
                            <span className="text-primary/70 tabular-nums">✓ {b.hits ?? 0}</span>
                            <span className="text-muted-foreground tabular-nums">— {b.misses ?? 0}</span>
                            {(b.failed ?? 0) > 0 && (
                                <span className="text-red-400 tabular-nums">✗ {b.failed}</span>
                            )}
                        </>
                    ) : b.processed > 0 ? (
                        <span className="text-muted-foreground tabular-nums">{b.processed}/{b.total}</span>
                    ) : null}
                </span>
            </button>

            <AnimatePresence>
                {open && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.18 }}
                        className="overflow-hidden"
                    >
                        <div className="mx-4 mb-3 rounded-lg border border-border/60 bg-muted/30 overflow-hidden">
                            <div className="h-1.5 w-full bg-muted">
                                <motion.div
                                    className="h-full bg-primary"
                                    initial={{ width: 0 }}
                                    animate={{ width: `${pct}%` }}
                                    transition={{ duration: 0.5, ease: "easeOut" }}
                                />
                            </div>
                            <div className="grid grid-cols-5 divide-x divide-border/60">
                                {statCells.map((s) => (
                                    <div key={s.label} className="flex flex-col items-center py-4 px-2 gap-1">
                                        <span className="text-xs text-muted-foreground">{s.label}</span>
                                        <span className={cn("text-xl font-bold tabular-nums", s.color)}>{s.value}</span>
                                        {s.sub && (
                                            <span className="text-xs text-muted-foreground tabular-nums">{s.sub}</span>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
