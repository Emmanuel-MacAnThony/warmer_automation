import { Mail } from "lucide-react";

export function NoTableSelected() {
    return (
        <div className="flex flex-col items-center justify-center h-64 text-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-muted flex items-center justify-center">
                <Mail size={20} className="text-muted-foreground" />
            </div>
            <div>
                <p className="text-xs font-mono font-medium uppercase tracking-widest text-muted-foreground">
                    No table selected
                </p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                    Set a Base ID and Table ID in the Dashboard first
                </p>
            </div>
        </div>
    );
}
