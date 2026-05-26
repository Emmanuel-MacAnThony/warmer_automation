import { type ScoreBreakdown } from "@/shared/api/client";
import { motion } from "framer-motion";
import { useState } from "react";
import { WHEEL_SEGS } from "../constants";
import { shade } from "../utils";

export function ScoreWheel({
    score,
    composite,
    onOpen,
}: {
    score: ScoreBreakdown;
    composite: number;
    onOpen?: () => void;
}) {
    const [hovered, setHovered] = useState<number | null>(null);

    const BW = 28,
        DX = 12,
        DY = 6,
        GAP = 13,
        CH = 60,
        TOP = 8;
    const N = WHEEL_SEGS.length;
    const W = N * (BW + GAP) - GAP + DX + 4;
    const H = CH + DY + TOP + 22;

    return (
        <div>
            <div className="flex items-baseline gap-2 mb-3">
                <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground/40">
                    Score
                </p>
                <p className="text-xs font-mono tabular-nums text-muted-foreground/55">
                    {Math.round(composite * 100)}%
                </p>
            </div>
            <svg
                viewBox={`0 0 ${W} ${H}`}
                width="100%"
                style={{ overflow: "visible" }}
            >
                <line
                    x1={0}
                    y1={TOP + CH}
                    x2={W - DX}
                    y2={TOP + CH}
                    stroke="currentColor"
                    strokeOpacity={0.08}
                    strokeWidth={0.8}
                />
                {WHEEL_SEGS.map((seg, i) => {
                    const val =
                        (score as unknown as Record<string, number>)[seg.key] ??
                        0;
                    const h = val * CH;
                    const bx = i * (BW + GAP);
                    const by = TOP + CH;
                    const ox = bx + BW / 2;

                    const front = `M${bx},${by} L${bx + BW},${by} L${bx + BW},${by - h} L${bx},${by - h}Z`;
                    const side = `M${bx + BW},${by} L${bx + BW + DX},${by - DY} L${bx + BW + DX},${by - DY - h} L${bx + BW},${by - h}Z`;
                    const top = `M${bx},${by - h} L${bx + BW},${by - h} L${bx + BW + DX},${by - h - DY} L${bx + DX},${by - h - DY}Z`;

                    const TW = Math.max(52, seg.label.length * 5 + 20);
                    const TH = 28;
                    const tx = Math.max(0, Math.min(W - TW, ox - TW / 2));
                    const ty = Math.max(2, by - h - DY - TH - 5);
                    const clipId = `bar-clip-${seg.key}`;

                    return (
                        <g
                            key={seg.key}
                            onMouseEnter={() => setHovered(i)}
                            onMouseLeave={() => setHovered(null)}
                            onClick={onOpen}
                            style={{ cursor: onOpen ? "pointer" : "default" }}
                        >
                            <defs>
                                <clipPath id={clipId}>
                                    <motion.rect
                                        x={bx - 1}
                                        width={BW + DX + 2}
                                        initial={{ y: by, height: 0 }}
                                        animate={{
                                            y: by - h - DY - 1,
                                            height: h + DY + 1,
                                        }}
                                        transition={{
                                            type: "tween",
                                            duration: 1.1,
                                            ease: [0.4, 0, 0.2, 1],
                                            delay: i * 0.1,
                                        }}
                                    />
                                </clipPath>
                            </defs>
                            <path
                                d={`M${bx},${by} L${bx + BW},${by} L${bx + BW},${TOP} L${bx},${TOP}Z`}
                                fill={seg.color}
                                fillOpacity={0.05}
                            />
                            <g
                                clipPath={`url(#${clipId})`}
                                style={{
                                    filter:
                                        hovered === i
                                            ? `brightness(1.3) drop-shadow(0 0 5px ${seg.color}90)`
                                            : "none",
                                    transition: "filter 0.15s ease",
                                }}
                            >
                                <path d={front} fill={seg.color} />
                                <path d={side} fill={shade(seg.color, 0.52)} />
                                {h > 0.5 && (
                                    <path
                                        d={top}
                                        fill={shade(seg.color, 1.2)}
                                    />
                                )}
                            </g>
                            {h > 4 && (
                                <motion.text
                                    x={ox}
                                    textAnchor="middle"
                                    fill="currentColor"
                                    initial={{ y: by, opacity: 0 }}
                                    animate={{
                                        y: by - h - DY - 4,
                                        opacity: 0.5,
                                    }}
                                    transition={{
                                        type: "tween",
                                        duration: 1.1,
                                        ease: [0.4, 0, 0.2, 1],
                                        delay: i * 0.1,
                                    }}
                                    style={{
                                        fontSize: 7,
                                        fontFamily: "inherit",
                                    }}
                                >
                                    {Math.round(val * 100)}
                                </motion.text>
                            )}
                            <text
                                x={ox}
                                y={by + DY + 13}
                                textAnchor="middle"
                                fill="currentColor"
                                style={{
                                    fontSize: 7.5,
                                    fontFamily: "inherit",
                                    opacity: 0.35,
                                    letterSpacing: "0.03em",
                                }}
                            >
                                {seg.short}
                            </text>
                            {hovered === i && (
                                <g>
                                    <rect
                                        x={tx}
                                        y={ty}
                                        width={TW}
                                        height={TH}
                                        rx={3}
                                        fill={seg.color}
                                        fillOpacity={0.93}
                                    />
                                    <text
                                        x={tx + TW / 2}
                                        y={ty + 11}
                                        textAnchor="middle"
                                        fill="white"
                                        style={{
                                            fontSize: 7.5,
                                            fontFamily: "inherit",
                                            fontWeight: 600,
                                        }}
                                    >
                                        {seg.label}
                                    </text>
                                    <text
                                        x={tx + TW / 2}
                                        y={ty + 22}
                                        textAnchor="middle"
                                        fill="white"
                                        fillOpacity={0.75}
                                        style={{
                                            fontSize: 7.5,
                                            fontFamily: "inherit",
                                            fontVariantNumeric: "tabular-nums",
                                        }}
                                    >
                                        {Math.round(val * 100)}%
                                    </text>
                                </g>
                            )}
                        </g>
                    );
                })}
            </svg>
        </div>
    );
}
