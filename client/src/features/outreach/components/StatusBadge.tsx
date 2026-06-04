import { cn } from "@/shared/lib/utils";
import type { Campaign } from "@/shared/api/client";

export function StatusBadge({ status }: { status: Campaign["status"] }) {
    const styles: Record<string, string> = {
        ready:       "bg-teal-300/10 text-teal-300 border-teal-300/20",
        in_progress: "bg-blue-500/10    text-blue-400    border-blue-500/20",
        segmenting:  "bg-amber-500/10   text-amber-400   border-amber-500/20",
        failed:      "bg-red-500/10     text-red-400     border-red-500/20",
        draft:       "bg-muted/60 text-muted-foreground/60 border-transparent",
        completed:   "bg-muted/60 text-muted-foreground/60 border-transparent",
    };
    return (
        <span
            className={cn(
                "inline-flex items-center px-1.5 py-0.5 rounded border text-xs font-mono uppercase tracking-wide",
                styles[status] ?? styles.draft,
            )}
        >
            {status}
        </span>
    );
}
