import { motion } from "framer-motion";
import { useEffect, useState } from "react";

export function MiniDonut({ poolPct, color }: { poolPct: number; color: string }) {
    const R = 20, CX = 26, CY = 26, SW = 7;
    const circ = 2 * Math.PI * R;
    const filledDash = (poolPct / 100) * circ;
    const emptyDash = circ - filledDash;

    const [displayPct, setDisplayPct] = useState(0);
    useEffect(() => {
        let frame: number;
        let start: number | null = null;
        const duration = 900;
        const step = (ts: number) => {
            if (!start) start = ts;
            const progress = Math.min((ts - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            setDisplayPct(Math.round(eased * poolPct));
            if (progress < 1) frame = requestAnimationFrame(step);
        };
        frame = requestAnimationFrame(step);
        return () => cancelAnimationFrame(frame);
    }, [poolPct]);

    return (
        <svg width={52} height={52} viewBox="0 0 52 52" className="shrink-0">
            <circle
                cx={CX} cy={CY} r={R} fill="none"
                stroke="currentColor" strokeWidth={SW}
                className="text-muted/60"
                strokeDasharray={`${circ} 0`}
            />
            {poolPct > 0 && (
                <motion.circle
                    cx={CX} cy={CY} r={R} fill="none"
                    stroke={color} strokeWidth={SW}
                    initial={{ strokeDasharray: `0 ${circ}` }}
                    animate={{ strokeDasharray: `${filledDash} ${emptyDash}` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    style={{ transform: "rotate(-90deg)", transformOrigin: `${CX}px ${CY}px` }}
                />
            )}
            <motion.text
                x={CX} y={CY + 1} textAnchor="middle" dominantBaseline="middle"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                style={{ fontSize: 9, fontFamily: "monospace", fill: color, fontWeight: 600 }}
            >
                {displayPct}%
            </motion.text>
        </svg>
    );
}
