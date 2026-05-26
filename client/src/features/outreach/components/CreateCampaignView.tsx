import { Button } from "@/shared/components/ui/button";
import { ArrowLeft, FileText, Loader2, Megaphone, Paperclip, X } from "lucide-react";
import { useRef, useState } from "react";
import { useOutreachContext } from "../context/OutreachContext";

export function CreateCampaignView() {
    const { goal, setGoal, creating, handleCreate, setView } = useOutreachContext();
    const [deck, setDeck] = useState<File | null>(null);
    const deckInputRef = useRef<HTMLInputElement>(null);

    return (
        <div className="p-6 w-full max-w-xl space-y-6">
            <button
                onClick={() => setView("list")}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
                <ArrowLeft size={12} /> Back
            </button>
            <div>
                <h1 className="font-mono text-2xl font-bold tracking-tight">New Campaign</h1>
                <p className="text-sm text-muted-foreground mt-1">AI-powered contact segmentation</p>
            </div>
            <div className="space-y-3">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground/50">Goal</label>
                <textarea
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    placeholder="e.g. Raise $500k for the cancer research fund by Q3 from warm connections in healthcare and tech"
                    rows={4}
                    className="w-full rounded-lg border border-border bg-background px-3.5 py-3 text-sm resize-none focus:outline-none focus:border-primary/50 transition-colors placeholder:text-muted-foreground/30 leading-relaxed text-foreground/80"
                />
                <p className="text-xs text-muted-foreground/40">
                    Contacts are scored on 6 signals: giving history, warm paths, campaign match, capacity, trajectory, and engagement.
                </p>
            </div>

            {/* Optional campaign deck */}
            <div className="space-y-2">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground/50">
                    Campaign deck <span className="normal-case tracking-normal text-muted-foreground/30">(optional)</span>
                </label>
                <input
                    ref={deckInputRef}
                    type="file"
                    accept=".pdf,.docx,.doc,.txt"
                    className="hidden"
                    onChange={(e) => setDeck(e.target.files?.[0] ?? null)}
                />
                {deck ? (
                    <div className="flex items-center gap-2.5 rounded-md border border-emerald-500/25 bg-emerald-500/8 px-3 py-2">
                        <FileText size={13} className="text-emerald-400 shrink-0" />
                        <span className="flex-1 text-[12px] font-mono text-foreground/80 truncate">{deck.name}</span>
                        <button onClick={() => setDeck(null)} className="text-muted-foreground/40 hover:text-red-400 transition-colors shrink-0">
                            <X size={13} />
                        </button>
                    </div>
                ) : (
                    <button
                        onClick={() => deckInputRef.current?.click()}
                        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-md border border-dashed border-border/40 text-[12px] text-muted-foreground/50 hover:text-foreground/70 hover:border-border/60 hover:bg-muted/10 transition-colors"
                    >
                        <Paperclip size={12} /> Attach a deck or brief (PDF, DOCX, TXT)
                    </button>
                )}
                <p className="text-xs text-muted-foreground/40">
                    Optional. If attached, the email copilot grounds drafts in your real campaign messaging instead of generic copy.
                </p>
            </div>

            <Button onClick={() => handleCreate(deck ?? undefined)} disabled={creating || goal.trim().length < 10} className="gap-2">
                {creating ? <Loader2 size={13} className="animate-spin" /> : <Megaphone size={13} />}
                {creating ? "Creating campaign..." : "Create campaign"}
            </Button>
        </div>
    );
}
