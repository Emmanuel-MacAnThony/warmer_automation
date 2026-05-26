import { cn } from "@/shared/lib/utils";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FIELD_GROUPS } from "../constants";

interface Rect {
    top: number;
    bottom: number;
    left: number;
}

interface Props {
    query: string;
    anchorRect: Rect;
    onSelect: (field: string) => void;
    onClose: () => void;
    enrichedFields?: string[];
}

export function VariablePicker({ query, anchorRect, onSelect, onClose, enrichedFields }: Props) {
    const ref = useRef<HTMLDivElement>(null);
    const [activeIdx, setActiveIdx] = useState(0);

    const enrichedItems = (enrichedFields ?? []).map((f) => ({ field: f, group: "Enriched" }));
    const staticItems = Object.entries(FIELD_GROUPS).flatMap(([group, fields]) =>
        fields.map((f) => ({ field: f, group })),
    );
    const all = [...enrichedItems, ...staticItems];

    const q = query.toLowerCase().trim();
    const filtered = q ? all.filter(({ field }) => field.toLowerCase().includes(q)) : all;
    const flat = filtered.map((i) => i.field);

    useEffect(() => { setActiveIdx(0); }, [q]);

    // Keep a stable ref to avoid re-subscribing on every render
    const stateRef = useRef({ flat, activeIdx, onSelect, onClose });
    stateRef.current = { flat, activeIdx, onSelect, onClose };

    useEffect(() => {
        const handle = (e: KeyboardEvent) => {
            const { flat, activeIdx, onSelect, onClose } = stateRef.current;
            if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
            if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(i + 1, flat.length - 1)); return; }
            if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx((i) => Math.max(i - 1, 0)); return; }
            if (e.key === "Enter" && flat[activeIdx]) { e.preventDefault(); e.stopPropagation(); onSelect(flat[activeIdx]); }
        };
        window.addEventListener("keydown", handle, true);
        return () => window.removeEventListener("keydown", handle, true);
    }, []);

    useEffect(() => {
        const handle = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) onClose();
        };
        window.addEventListener("mousedown", handle);
        return () => window.removeEventListener("mousedown", handle);
    }, [onClose]);

    if (filtered.length === 0) return null;

    const grouped: { group: string; fields: string[] }[] = [];
    for (const { field, group } of filtered) {
        const existing = grouped.find((g) => g.group === group);
        if (existing) existing.fields.push(field);
        else grouped.push({ group, fields: [field] });
    }

    const viewH = window.innerHeight;
    const estimatedH = Math.min(grouped.length * 26 + filtered.length * 32 + 8, 280);
    const top = anchorRect.bottom + 4 + estimatedH > viewH
        ? anchorRect.top - estimatedH - 4
        : anchorRect.bottom + 4;

    return createPortal(
        <div
            ref={ref}
            style={{ top, left: anchorRect.left, minWidth: 200 }}
            className="fixed z-9999 rounded-md border border-border/60 bg-popover/95 backdrop-blur-sm shadow-lg overflow-y-auto max-h-70 py-1"
        >
            {grouped.map(({ group, fields }) => (
                <div key={group}>
                    <p className="px-3 pt-2 pb-0.5 text-[9px] font-mono uppercase tracking-widest text-muted-foreground/40">
                        {group}
                    </p>
                    {fields.map((f) => {
                        const i = flat.indexOf(f);
                        return (
                            <button
                                key={f}
                                onMouseDown={(e) => { e.preventDefault(); onSelect(f); }}
                                className={cn(
                                    "w-full text-left px-3 py-1.5 text-[12px] font-mono transition-colors",
                                    i === activeIdx
                                        ? "bg-primary/15 text-primary"
                                        : "text-foreground/70 hover:bg-muted/50 hover:text-foreground",
                                )}
                            >
                                <span className="text-muted-foreground/40">[</span>
                                {f}
                                <span className="text-muted-foreground/40">]</span>
                            </button>
                        );
                    })}
                </div>
            ))}
        </div>,
        document.body,
    );
}
