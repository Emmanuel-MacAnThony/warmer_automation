import { cn } from "@/shared/lib/utils";
import { Plugin, PluginKey } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import type { MutableRefObject } from "react";
import { KNOWN_FIELDS, SLOT_RE } from "./constants";

export const sentenceCase = (s: string) =>
    s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

export function parseSegError(raw: string): string {
    if (raw.includes("NOT_FOUND") || raw.includes("404"))
        return "Table not found — check your Base ID and Table ID in Dashboard";
    if (raw.includes("AUTHENTICATION_REQUIRED") || raw.includes("401"))
        return "Airtable authentication failed — check your API key";
    if (raw.includes("FORBIDDEN") || raw.includes("403"))
        return "No permission to access this table — check your Airtable API key";
    if (raw.includes("embedding") || raw.includes("OpenAI"))
        return "Goal embedding failed — check your OpenAI API key";
    return raw.length > 120 ? raw.slice(0, 120) + "…" : raw;
}

export function formatSignalValue(raw: string): string {
    const normalise = (s: string) => {
        const t = s.replace(/_/g, " ").trim();
        const isTag =
            t === t.toUpperCase() && t.length < 40 && !/[.!?,]/.test(t);
        const base = isTag ? t.toLowerCase() : t;
        return base.charAt(0).toUpperCase() + base.slice(1);
    };
    if (raw.startsWith("[") && raw.endsWith("]")) {
        try {
            const arr: unknown[] = JSON.parse(raw.replace(/'/g, '"'));
            if (Array.isArray(arr))
                return arr.map((s) => normalise(String(s))).join(", ");
        } catch {}
    }
    return normalise(raw);
}

export function highlightSlots(text: string, knownSet: Set<string> = new Set()) {
    return text
        .split(
            /(\[[A-Za-z][A-Za-z0-9 _/.-]*(?:\s*\|\s*fallback:\s*"[^"]*")?\])/,
        )
        .map((part, i) => {
            if (!/^\[/.test(part)) return <span key={i}>{part}</span>;
            const name = part
                .replace(/^\[/, "")
                .replace(/[|\]].*/s, "")
                .trim();
            const hasFallback = /\|\s*fallback:/i.test(part);
            const mapped = name in KNOWN_FIELDS || knownSet.has(name);
            return (
                <mark
                    key={i}
                    className={cn(
                        "rounded-[2px] not-italic",
                        mapped
                            ? "bg-emerald-500/15 text-emerald-400/80"
                            : hasFallback
                              ? "bg-blue-500/15 text-blue-400/70"
                              : "bg-amber-500/20 text-amber-400",
                    )}
                >
                    {part}
                </mark>
            );
        });
}

export function shade(hex: string, f: number): string {
    const c = (o: number) =>
        Math.min(255, Math.round(parseInt(hex.slice(o, o + 2), 16) * f));
    return `rgb(${c(1)},${c(3)},${c(5)})`;
}

// Known fallback phrases, mirroring variable_resolver.py _DEFAULT_FALLBACKS
const _SLOT_FALLBACKS: Record<string, string> = {
    first_name:       "there",
    company:          "",
    title:            "",
    topic_hook:       "",
    giving_reference: "your commitment to this work",
    capacity_close:   "a contribution at any level",
    warm_opener:      "",
};

/**
 * Add | fallback: "..." to any bare [variable] slot that doesn't already have one.
 * Applied after AI generation and file parsing so the user sees fallbacks up-front.
 */
export function withFallbacks(text: string): string {
    // Matches [name] where name contains no | — i.e. no existing fallback
    return text.replace(/\[([A-Za-z][A-Za-z0-9 _/.-]*)\]/g, (_, name) => {
        const fb = name in _SLOT_FALLBACKS ? _SLOT_FALLBACKS[name] : "";
        return `[${name} | fallback: "${fb}"]`;
    });
}

export function textToHtml(text: string): string {
    if (!text) return "";
    return text
        .split("\n")
        .map((line) => `<p>${line || "<br>"}</p>`)
        .join("");
}

export function makeSlotPlugin(
    knownRef: MutableRefObject<Set<string> | undefined>,
) {
    return new Plugin({
        key: new PluginKey("slotHighlighter"),
        props: {
            decorations(state) {
                const decos: Decoration[] = [];
                state.doc.descendants((node, pos) => {
                    if (!node.isText || !node.text) return;
                    const re = new RegExp(SLOT_RE.source, "g");
                    let m: RegExpExecArray | null;
                    while ((m = re.exec(node.text)) !== null) {
                        const name = m[0]
                            .replace(/^\[/, "")
                            .replace(/[|\]].*/s, "")
                            .trim();
                        const hasFb = /\|.*fallback:/i.test(m[0]);
                        const mapped =
                            name in KNOWN_FIELDS ||
                            (knownRef.current?.has(name) ?? false);
                        const cls = mapped
                            ? "slot-mapped"
                            : hasFb
                              ? "slot-fallback"
                              : "slot-unmapped";
                        decos.push(
                            Decoration.inline(
                                pos + m.index,
                                pos + m.index + m[0].length,
                                { class: `slot-chip ${cls}` },
                            ),
                        );
                    }
                });
                return DecorationSet.create(state.doc, decos);
            },
        },
    });
}
