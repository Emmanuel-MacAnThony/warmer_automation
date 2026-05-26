import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { SIGNAL_META } from "../constants";
import { useOutreachContext } from "../context/OutreachContext";
import { StreamingMessage } from "./StreamingMessage";

export function SignalsDrawer() {
    const { queue, queueIdx, showSignals, setShowSignals } = useOutreachContext();
    const contact = queue[queueIdx] ?? null;
    const snap = contact?.contact_snapshot;
    const signals = snap?.signals;

    const items = contact ? [
        ...SIGNAL_META
            .filter(({ key }) => signals?.[key as keyof typeof signals])
            .map(({ key, label, color }) => ({ key, label, color, isWarm: false })),
        ...(contact.warm_path_data?.connector
            ? [{ key: "warm_path", label: "Warm Path", color: "#a78bfa", isWarm: true }]
            : []),
    ] : [];

    return (
        <AnimatePresence>
            {showSignals && (
                <>
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        onClick={() => setShowSignals(false)}
                        className="absolute inset-0 bg-background/60 backdrop-blur-[2px]"
                    />
                    <motion.div
                        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
                        transition={{ type: "spring", damping: 28, stiffness: 320 }}
                        className="absolute inset-y-0 right-0 w-96 bg-background border-l flex flex-col overflow-hidden"
                    >
                        <div className="flex items-center justify-between px-5 py-3.5 border-b shrink-0">
                            <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground/50">Signals</p>
                            <button
                                onClick={() => setShowSignals(false)}
                                className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground/40 hover:text-foreground/70 hover:bg-muted transition-colors"
                            >
                                <X size={13} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto px-5 py-4">
                            <div>
                                {items.map(({ key, label, color, isWarm }, idx) => {
                                    const isLast = idx === items.length - 1;
                                    return (
                                        <div key={key} className="flex gap-3">
                                            <div className="flex flex-col items-center" style={{ width: 8 }}>
                                                <div className="h-2 w-2 rounded-full shrink-0 mt-0.75" style={{ backgroundColor: color }} />
                                                {!isLast && <div className="w-px flex-1 min-h-3 mt-1" style={{ backgroundColor: color + "30" }} />}
                                            </div>
                                            <div className={cn("flex-1 min-w-0", !isLast && "pb-7")}>
                                                <p className="text-xs font-mono uppercase tracking-wide text-muted-foreground/45 mb-0.5">{label}</p>
                                                {isWarm ? (
                                                    <>
                                                        <p className="leading-relaxed" style={{ color, fontSize: 11 }}>
                                                            <StreamingMessage
                                                                text={`You → ${contact!.warm_path_data!.connector} → ${snap?.name}`}
                                                                isActive={false}
                                                            />
                                                        </p>
                                                        {contact!.warm_path_data!.evidence && (
                                                            <p className="mt-1 leading-relaxed" style={{ color, fontSize: 11, opacity: 0.65 }}>
                                                                <StreamingMessage text={contact!.warm_path_data!.evidence} isActive={false} />
                                                            </p>
                                                        )}
                                                    </>
                                                ) : (() => {
                                                    const raw = signals![key as keyof typeof signals]
                                                    const items = Array.isArray(raw)
                                                        ? raw as string[]
                                                        : typeof raw === 'string' && raw.startsWith('[')
                                                            ? (raw.replace(/^\[|\]$/g, '').split(',').map(s => s.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean))
                                                            : null
                                                    return items ? (
                                                        <div className="flex flex-wrap gap-1 mt-0.5">
                                                            {items.map(item => (
                                                                <span
                                                                    key={item}
                                                                    className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] tracking-wide"
                                                                    style={{ backgroundColor: color + '18', color }}
                                                                >
                                                                    {item}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    ) : (
                                                        <p className="leading-relaxed" style={{ color, fontSize: 11 }}>
                                                            <StreamingMessage text={String(raw)} isActive={false} />
                                                        </p>
                                                    )
                                                })()}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}
