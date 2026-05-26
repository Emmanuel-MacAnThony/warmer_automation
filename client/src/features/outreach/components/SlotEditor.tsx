import { cn } from "@/shared/lib/utils";
import { Extension } from "@tiptap/core";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
    AlignCenter,
    AlignJustify,
    AlignLeft,
    AlignRight,
    Bold,
    Heading1,
    Heading2,
    Italic,
    List,
    ListOrdered,
    Redo2,
    Underline as UnderlineIcon,
    Undo2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { makeSlotPlugin, textToHtml, withFallbacks } from "../utils";
import { VariablePicker } from "./VariablePicker";

function TBtn({
    active,
    onClick,
    title,
    children,
}: {
    active?: boolean;
    onClick: () => void;
    title: string;
    children: React.ReactNode;
}) {
    return (
        <button
            type="button"
            title={title}
            onMouseDown={(e) => {
                e.preventDefault();
                onClick();
            }}
            className={cn(
                "h-6 w-6 rounded flex items-center justify-center transition-colors shrink-0",
                active
                    ? "bg-foreground/12 text-foreground"
                    : "text-foreground/50 hover:text-foreground hover:bg-muted/60",
            )}
        >
            {children}
        </button>
    );
}

export function SlotEditor({
    value,
    onChange,
    disabled,
    placeholder = "",
    knownSet,
    enrichedFields,
    className,
}: {
    value: string;
    onChange: (v: string) => void;
    disabled?: boolean;
    placeholder?: string;
    knownSet?: Set<string>;
    enrichedFields?: string[];
    className?: string;
}) {
    const [editorH, setEditorH] = useState(280);
    const [suggestion, setSuggestion] = useState<{
        query: string;
        rect: { top: number; bottom: number; left: number };
    } | null>(null);

    const onResizeStart = (e: React.MouseEvent) => {
        e.preventDefault();
        const startY = e.clientY;
        const startH = editorH;
        const onMove = (mv: MouseEvent) => setEditorH(Math.max(120, startH + mv.clientY - startY));
        const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
    };

    const knownRef = useRef(knownSet);
    useEffect(() => {
        knownRef.current = knownSet;
    }, [knownSet]);

    const isHtml = (s: string) => !!s && s.trimStart().startsWith("<");
    const toContent = (s: string) => isHtml(s) ? s : textToHtml(s);

    // Track the last value we pushed INTO the editor so we can skip syncing
    // when the value change originated from the editor itself (user typing).
    const pushedRef = useRef<string>(value);

    const suggestionRef = useRef(suggestion);
    useEffect(() => { suggestionRef.current = suggestion; }, [suggestion]);

    const editor = useEditor({
        extensions: [
            StarterKit.configure({ code: false, codeBlock: false, horizontalRule: false }),
            Underline,
            TextAlign.configure({ types: ["heading", "paragraph"] }),
            Placeholder.configure({ placeholder }),
            Extension.create({
                name: "slotHighlighter",
                addProseMirrorPlugins: () => [makeSlotPlugin(knownRef)],
            }),
        ],
        content: toContent(value),
        editable: !disabled,
        onUpdate: ({ editor }) => {
            const html = editor.getHTML();
            pushedRef.current = html; // editor produced this value, don't re-push it
            onChange(html);
        },
    });

    useEffect(() => {
        if (!editor) return;
        if (pushedRef.current === value) return;
        pushedRef.current = value;
        editor.commands.setContent(toContent(value), { emitUpdate: false });
    }, [editor, value]);

    useEffect(() => {
        editor?.setEditable(!disabled);
    }, [disabled]);

    useEffect(() => {
        if (!editor) return;
        const check = () => {
            const { state, view } = editor;
            const { from } = state.selection;
            const textBefore = state.doc.textBetween(Math.max(0, from - 100), from, "\n", "\0");
            const match = textBefore.match(/\[([^[\]]*)$/);
            if (match) {
                const coords = view.coordsAtPos(from);
                setSuggestion({ query: match[1], rect: { top: coords.top, bottom: coords.bottom, left: coords.left } });
            } else {
                setSuggestion(null);
            }
        };
        const onBlur = () => setSuggestion(null);
        editor.on("update", check);
        editor.on("selectionUpdate", check);
        editor.on("blur", onBlur);
        return () => {
            editor.off("update", check);
            editor.off("selectionUpdate", check);
            editor.off("blur", onBlur);
        };
    }, [editor]);

    const insertField = (field: string) => {
        if (!editor) return;
        const sug = suggestionRef.current;
        if (!sug) return;
        const { from } = editor.state.selection;
        const queryLen = sug.query.length;
        const bracketPos = from - queryLen - 1;
        editor.chain().focus().deleteRange({ from: bracketPos, to: from }).insertContent(withFallbacks(`[${field}]`)).run();
        setSuggestion(null);
    };

    const e = editor;
    return (
        <>
        <div
            className={cn(
                "slot-editor rounded-md border border-border/40 bg-background flex flex-col",
                "focus-within:ring-1 focus-within:ring-ring/40",
                disabled && "opacity-60 pointer-events-none",
                className,
            )}
            style={{ height: editorH }}
        >
            <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-border/30 bg-muted/20 flex-wrap shrink-0">
                <TBtn active={e?.isActive("heading", { level: 1 })} onClick={() => e?.chain().focus().toggleHeading({ level: 1 }).run()} title="Heading 1">
                    <Heading1 size={15} />
                </TBtn>
                <TBtn active={e?.isActive("heading", { level: 2 })} onClick={() => e?.chain().focus().toggleHeading({ level: 2 }).run()} title="Heading 2">
                    <Heading2 size={15} />
                </TBtn>
                <div className="w-px h-3.5 bg-border/40 mx-1" />
                <TBtn active={e?.isActive("bold")} onClick={() => e?.chain().focus().toggleBold().run()} title="Bold">
                    <Bold size={15} />
                </TBtn>
                <TBtn active={e?.isActive("italic")} onClick={() => e?.chain().focus().toggleItalic().run()} title="Italic">
                    <Italic size={15} />
                </TBtn>
                <TBtn active={e?.isActive("underline")} onClick={() => e?.chain().focus().toggleUnderline().run()} title="Underline">
                    <UnderlineIcon size={15} />
                </TBtn>
                <div className="w-px h-3.5 bg-border/40 mx-1" />
                <TBtn active={e?.isActive({ textAlign: "left" })} onClick={() => e?.chain().focus().setTextAlign("left").run()} title="Align left">
                    <AlignLeft size={15} />
                </TBtn>
                <TBtn active={e?.isActive({ textAlign: "center" })} onClick={() => e?.chain().focus().setTextAlign("center").run()} title="Align center">
                    <AlignCenter size={15} />
                </TBtn>
                <TBtn active={e?.isActive({ textAlign: "right" })} onClick={() => e?.chain().focus().setTextAlign("right").run()} title="Align right">
                    <AlignRight size={15} />
                </TBtn>
                <TBtn active={e?.isActive({ textAlign: "justify" })} onClick={() => e?.chain().focus().setTextAlign("justify").run()} title="Justify">
                    <AlignJustify size={15} />
                </TBtn>
                <div className="w-px h-3.5 bg-border/40 mx-1" />
                <TBtn active={e?.isActive("bulletList")} onClick={() => e?.chain().focus().toggleBulletList().run()} title="Bullet list">
                    <List size={15} />
                </TBtn>
                <TBtn active={e?.isActive("orderedList")} onClick={() => e?.chain().focus().toggleOrderedList().run()} title="Numbered list">
                    <ListOrdered size={15} />
                </TBtn>
                <div className="w-px h-3.5 bg-border/40 mx-1" />
                <TBtn active={false} onClick={() => e?.chain().focus().undo().run()} title="Undo">
                    <Undo2 size={15} />
                </TBtn>
                <TBtn active={false} onClick={() => e?.chain().focus().redo().run()} title="Redo">
                    <Redo2 size={15} />
                </TBtn>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto">
                <EditorContent editor={editor} />
            </div>
            <div
                onMouseDown={onResizeStart}
                className="h-2.5 shrink-0 cursor-ns-resize flex items-center justify-center border-t border-border/20 hover:bg-muted/40 active:bg-muted/60 transition-colors"
            >
                <div className="w-8 h-0.5 rounded-full bg-border/50" />
            </div>
        </div>
        {suggestion && (
            <VariablePicker
                query={suggestion.query}
                anchorRect={suggestion.rect}
                onSelect={insertField}
                onClose={() => setSuggestion(null)}
                enrichedFields={enrichedFields}
            />
        )}
        </>
    );
}
