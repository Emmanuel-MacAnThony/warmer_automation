import { cn } from "@/shared/lib/utils";
import { Loader2, Upload } from "lucide-react";
import { useBatchCore } from "../../context/batch/BatchCoreContext";
import { useBatchEditor } from "../../context/batch/BatchEditorContext";

export function ChooseStep() {
    const { setStep } = useBatchCore();
    const { fileInputRef, uploadingFile, dragOver, setDragOver, handleFileUpload } = useBatchEditor();

    return (
        <div className="flex-1 flex items-center justify-center p-8">
            <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.docx,.doc,.pdf"
                className="hidden"
                onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFileUpload(f);
                    e.target.value = "";
                }}
            />
            <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    const f = e.dataTransfer.files[0];
                    if (f) handleFileUpload(f);
                }}
                className={cn(
                    "w-full max-w-lg rounded-xl border-2 border-dashed py-16 px-10 flex flex-col items-center gap-6 text-center transition-colors",
                    dragOver ? "border-primary/50 bg-primary/5" : "border-border/40 hover:border-border/70",
                )}
            >
                {uploadingFile ? (
                    <Loader2 size={32} className="text-muted-foreground/30 animate-spin" />
                ) : (
                    <Upload size={32} className="text-muted-foreground/25" />
                )}
                <div className="space-y-2">
                    <p className="text-base font-medium text-foreground">
                        {uploadingFile ? "Parsing file…" : "Drop your template here"}
                    </p>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                        {uploadingFile
                            ? "Extracting text and detecting [variable] slots…"
                            : "Accepts .txt, .docx or .pdf — write [Name] style placeholders for personalisation"}
                    </p>
                </div>
                {!uploadingFile && (
                    <div className="flex items-center gap-3 mt-2">
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            className="px-4 py-2 rounded-md text-sm border border-border/60 bg-muted/40 text-foreground hover:bg-muted/70 transition-colors"
                        >
                            Browse file
                        </button>
                        <span className="text-xs text-muted-foreground/50">or</span>
                        <button
                            onClick={() => setStep("editor")}
                            className="px-4 py-2 rounded-md text-sm bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 transition-colors"
                        >
                            Generate with AI
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
