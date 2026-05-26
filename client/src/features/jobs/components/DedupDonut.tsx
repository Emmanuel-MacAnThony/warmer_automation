import { motion } from "framer-motion";

export function DedupDonut({ checked, deleted }: { checked: number; deleted: number }) {
    const R = 16, CX = 20, CY = 20, SW = 6;
    const circ  = 2 * Math.PI * R;
    const pct   = checked > 0 ? Math.min(100, Math.round((deleted / checked) * 100)) : 0;
    const filled = (pct / 100) * circ;
    const color  = deleted === 0 ? "var(--color-primary)" : "#f59e0b";

    return (
        <svg width={40} height={40} viewBox="0 0 40 40" className="shrink-0">
            <circle cx={CX} cy={CY} r={R} fill="none" stroke="currentColor"
                strokeWidth={SW} className="text-muted/60" />
            {pct > 0 && (
                <motion.circle
                    cx={CX} cy={CY} r={R} fill="none" stroke={color} strokeWidth={SW}
                    initial={{ strokeDasharray: `0 ${circ}` }}
                    animate={{ strokeDasharray: `${filled} ${circ - filled}` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    style={{ transform: "rotate(-90deg)", transformOrigin: `${CX}px ${CY}px` }}
                />
            )}
            <text x={CX} y={CY + 1} textAnchor="middle" dominantBaseline="middle"
                style={{ fontSize: 7, fontFamily: "monospace", fill: color, fontWeight: 600 }}>
                {pct === 0 ? "✓" : `${pct}%`}
            </text>
        </svg>
    );
}
