import { motion } from "framer-motion";
import { useEffect, useState } from "react";

export function StreamingMessage({
    text,
    isActive,
}: {
    text: string;
    isActive: boolean;
}) {
    const [chars, setChars] = useState(0);

    useEffect(() => {
        setChars(0);
        if (!text) return;
        const speed = Math.max(3, Math.ceil(text.length / 18));
        let i = 0;
        let raf: number;
        const tick = () => {
            i = Math.min(i + speed, text.length);
            setChars(i);
            if (i < text.length) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(raf);
    }, [text]);

    const typing = chars < text.length;

    return (
        <span className="relative leading-relaxed overflow-hidden">
            {text.slice(0, chars)}
            {typing && (
                <motion.span
                    className="inline-block w-[2px] h-[0.85em] align-middle ml-px bg-current rounded-full"
                    animate={{ opacity: [1, 0.15, 1] }}
                    transition={{ duration: 0.45, repeat: Infinity }}
                />
            )}
            {isActive && !typing && (
                <motion.span
                    aria-hidden
                    className="absolute inset-0 pointer-events-none"
                    style={{
                        background:
                            "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.13) 50%, transparent 100%)",
                    }}
                    animate={{ x: ["-110%", "210%"] }}
                    transition={{
                        duration: 2.2,
                        repeat: Infinity,
                        ease: "linear",
                        repeatDelay: 0.9,
                    }}
                />
            )}
        </span>
    );
}
