import { api, type Campaign, type TierStat } from "@/shared/api/client";
import { Card } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, Mail, Megaphone, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { TIER_ROWS } from "../constants";
import type { Tier } from "../types";
import { sentenceCase } from "../utils";
import { MiniDonut } from "./MiniDonut";
import { StatusBadge } from "./StatusBadge";

export function CampaignCard({
    campaign,
    onOpen,
    onEnterTier,
    onDelete,
    initialTiersOpen = false,
    initialSelectedTier = null,
}: {
    campaign: Campaign;
    onOpen: () => void;
    onEnterTier: (tier: Tier) => void;
    onEnterBatch: (tier: Tier) => void;
    onDelete: () => void;
    initialTiersOpen?: boolean;
    initialSelectedTier?: Tier | null;
}) {
    const [tiersOpen, setTiersOpen] = useState(initialTiersOpen);
    const [openPreviews, setOpenPreviews] = useState<Set<Tier>>(
        initialSelectedTier ? new Set([initialSelectedTier]) : new Set(),
    );
    const [tierStats, setTierStats] = useState<Record<string, TierStat> | null>(null);

    const t1 = campaign.tier_1_count, t2 = campaign.tier_2_count, t3 = campaign.tier_3_count;
    const total = t1 + t2 + t3;
    const hasData = total > 0;
    const date = new Date(campaign.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const counts: Record<Tier, number> = { tier_1: t1, tier_2: t2, tier_3: t3 };
    const activeTiers = TIER_ROWS.filter((r) => counts[r.key] > 0);

    // React to parent re-opening the card (e.g. returning from BatchView)
    useEffect(() => { if (initialTiersOpen) setTiersOpen(true); }, [initialTiersOpen]);
    useEffect(() => {
        if (initialSelectedTier) setOpenPreviews(new Set([initialSelectedTier]));
    }, [initialSelectedTier]);

    // Always fetch immediately on expand, then poll every 5s while any tier is open.
    useEffect(() => {
        if (openPreviews.size === 0) return;
        api.getCampaignStats(campaign.id).then(setTierStats).catch(() => {});
        const t = setInterval(() => {
            api.getCampaignStats(campaign.id).then(setTierStats).catch(() => {});
        }, 5000);
        return () => clearInterval(t);
    }, [openPreviews.size, campaign.id]);

    const handleTierClick = (key: Tier) => {
        setOpenPreviews((prev) => {
            const next = new Set(prev);
            next.has(key) ? next.delete(key) : next.add(key);
            return next;
        });
    };

    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
            <Card className="overflow-hidden w-full">
                <div
                    onClick={onOpen}
                    className="flex items-center gap-3 px-4 py-2.5 border-b border-border/60 cursor-pointer hover:bg-muted/20 transition-colors"
                >
                    <Megaphone size={12} className="text-muted-foreground/50 shrink-0" />
                    <StatusBadge status={campaign.status} />
                    <span className="text-xs text-muted-foreground/60 font-mono truncate flex-1 min-w-0">
                        {hasData ? `${total.toLocaleString()} contacts` : "No contacts yet"}
                    </span>
                    <span className="text-[11px] font-mono text-muted-foreground/40 shrink-0">{date}</span>
                    <button
                        onClick={(e) => { e.stopPropagation(); onDelete(); }}
                        className="p-1 rounded hover:bg-red-500/10 hover:text-red-400 text-muted-foreground/20 transition-colors shrink-0"
                    >
                        <Trash2 size={12} />
                    </button>
                </div>

                <div className="px-4 py-3 cursor-pointer hover:bg-muted/10 transition-colors" onClick={onOpen}>
                    <p className="text-sm font-mono text-foreground/80 line-clamp-2 leading-snug">
                        {sentenceCase(campaign.goal)}
                    </p>
                    {campaign.emails_sent > 0 && (
                        <span className="inline-flex items-center gap-1.5 mt-2 px-2 py-0.5 rounded-md border border-emerald-500/25 bg-emerald-500/10 text-xs font-mono text-emerald-600 dark:text-emerald-400 tabular-nums">
                            <Mail size={11} /> {campaign.emails_sent.toLocaleString()} emails sent
                        </span>
                    )}
                </div>

                {hasData && (
                    <button
                        onClick={() => { setTiersOpen((o) => !o); setOpenPreviews(new Set()); }}
                        className="w-full flex items-center gap-2 px-4 py-2 border-t border-border hover:bg-muted/40 transition-colors text-xs text-muted-foreground"
                    >
                        <ChevronRight
                            size={13}
                            className={cn("transition-transform duration-150", tiersOpen && "rotate-90")}
                        />
                        {activeTiers.length} tier{activeTiers.length !== 1 ? "s" : ""}
                    </button>
                )}

                <AnimatePresence>
                    {tiersOpen && (
                        <motion.div
                            initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }}
                            transition={{ duration: 0.2 }} className="overflow-hidden"
                        >
                            {activeTiers.map((r) => {
                                const isSelected = openPreviews.has(r.key);
                                return (
                                    <div key={r.key}>
                                        <div
                                            className={cn(
                                                "w-full flex items-center gap-3 px-4 py-3 border-t border-border/40 transition-colors",
                                                isSelected ? "bg-muted/40" : "hover:bg-muted/20",
                                            )}
                                        >
                                            <button
                                                onClick={() => handleTierClick(r.key)}
                                                className="flex items-center gap-3 flex-1 min-w-0 text-left"
                                            >
                                                <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-[11px] font-medium shrink-0", r.badge)}>
                                                    <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", r.dot)} />
                                                    {r.label}
                                                </span>
                                                <span className="text-xs text-muted-foreground/50 hidden sm:inline truncate">
                                                    {r.desc.split(" — ")[0]}
                                                </span>
                                                <span className="ml-auto text-sm font-mono font-semibold tabular-nums text-foreground/60">
                                                    {counts[r.key].toLocaleString()}
                                                </span>
                                            </button>
                                            <ChevronRight
                                                size={13}
                                                onClick={() => handleTierClick(r.key)}
                                                className={cn(
                                                    "cursor-pointer transition-transform duration-150 text-muted-foreground/30 shrink-0",
                                                    isSelected && "rotate-90 text-muted-foreground/60",
                                                )}
                                            />
                                        </div>

                                        <AnimatePresence>
                                            {isSelected && (
                                                <motion.div
                                                    initial={{ height: 0, opacity: 0 }}
                                                    animate={{ height: "auto", opacity: 1 }}
                                                    exit={{ height: 0, opacity: 0 }}
                                                    transition={{ duration: 0.18 }}
                                                    className="overflow-hidden"
                                                >
                                                    <div className="border-t border-border/40 bg-muted/20">
                                                        {(() => {
                                                            const s: TierStat = tierStats?.[r.key] ?? {
                                                                pending: counts[r.key],
                                                                sent: 0,
                                                                skipped: 0,
                                                                later: 0,
                                                                total: counts[r.key],
                                                                template_status: null,
                                                                latest_job: null,
                                                            };
                                                            // A tier can have many templates / sends, so summing "emails sent"
                                                            // is ambiguous. "Reached" = distinct contacts emailed at least once,
                                                            // which is unambiguous regardless of how many templates target the tier.
                                                            const reached = s.sent;
                                                            const coverage = s.total > 0 ? Math.round((reached / s.total) * 100) : 0;
                                                            const st = [
                                                                { label: "Leads", display: s.total.toLocaleString(), color: "text-emerald-400/80" },
                                                                { label: "Of Pool", display: `${Math.round((s.total / total) * 100)}%`, color: "text-emerald-400/80" },
                                                                { label: "Reached", display: reached.toLocaleString(), color: reached > 0 ? "text-emerald-500" : "text-muted-foreground/50" },
                                                                { label: "Coverage", display: `${coverage}%`, color: coverage > 0 ? "text-emerald-500" : "text-muted-foreground/50" },
                                                            ];
                                                            return (
                                                                <div>
                                                                    <div className="flex items-stretch">
                                                                        <div className="flex items-center justify-center px-4 py-3 border-r border-border/40">
                                                                            <MiniDonut
                                                                                poolPct={Math.round((s.total / total) * 100)}
                                                                                color={r.hex}
                                                                            />
                                                                        </div>
                                                                        <div className="flex flex-1 divide-x divide-border/40">
                                                                            {st.map((st) => (
                                                                                <div key={st.label} className="flex-1 flex flex-col justify-center px-3 py-3">
                                                                                    <p className={cn("text-xs font-semibold tabular-nums leading-none", st.color)}>
                                                                                        {st.display}
                                                                                    </p>
                                                                                    <p className="font-mono text-[9px] text-muted-foreground/40 tracking-widest uppercase mt-1">
                                                                                        {st.label}
                                                                                    </p>
                                                                                </div>
                                                                            ))}
                                                                        </div>
                                                                        <div className="flex items-center px-3 border-l border-border/40">
                                                                            <button
                                                                                onClick={() => onEnterTier(r.key)}
                                                                                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors font-medium"
                                                                            >
                                                                                Open <ChevronRight size={11} />
                                                                            </button>
                                                                        </div>
                                                                    </div>

                                                                </div>
                                                            );
                                                        })()}
                                                    </div>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>
                                );
                            })}
                        </motion.div>
                    )}
                </AnimatePresence>
            </Card>
        </motion.div>
    );
}
