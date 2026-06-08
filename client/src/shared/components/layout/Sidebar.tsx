import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import {
    Briefcase,
    LayoutDashboard,
    /* GitBranch, */ Mail,
} from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

const EXPANDED = 224;
const COLLAPSED = 60;

const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", to: "/" },
    { icon: Briefcase, label: "Enrichment", to: "/jobs" },
    // { icon: GitBranch,       label: 'Mappings',  to: '/mappings' },
    { icon: Mail, label: "Outreach", to: "/outreach" },
    // { icon: Wrench, label: 'Utils', to: '/utils' },
] as const;

export function Sidebar() {
    const [collapsed, setCollapsed] = useState(
        () => localStorage.getItem("sidebar-collapsed") === "true",
    );
    const location = useLocation();

    const toggle = () => {
        setCollapsed((c) => {
            const next = !c;
            localStorage.setItem("sidebar-collapsed", String(next));
            return next;
        });
    };

    return (
        <motion.aside
            animate={{ width: collapsed ? COLLAPSED : EXPANDED }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            className="relative flex flex-col border-r border-sidebar-border bg-sidebar shrink-0 overflow-hidden"
            style={{ minWidth: collapsed ? COLLAPSED : EXPANDED }}
        >
            {/* Brand — click to collapse/expand */}
            <button
                onClick={toggle}
                className="flex h-14 items-center px-3 border-b border-sidebar-border shrink-0 w-full hover:bg-sidebar-accent/50 transition-colors duration-150 group"
            >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/40 bg-primary/8 shrink-0">
                    <span className="font-mono text-base font-bold text-primary leading-none">
                        W
                    </span>
                </div>
                <AnimatePresence>
                    {!collapsed && (
                        <motion.span
                            initial={{ opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -8 }}
                            transition={{ duration: 0.15 }}
                            className="ml-3 font-mono font-bold text-sm tracking-widest uppercase text-sidebar-foreground whitespace-nowrap"
                        >
                            Warmer
                        </motion.span>
                    )}
                </AnimatePresence>
            </button>

            {/* Nav */}
            <nav className="flex-1 py-3 space-y-0.5 px-2 overflow-y-auto">
                {navItems.map((item) => {
                    const active = location.pathname === item.to;
                    const link = (
                        <Link
                            to={item.to}
                            className={cn(
                                "flex items-center gap-3 py-2.5 rounded-md transition-all duration-150",
                                collapsed ? "px-2.5 justify-center" : "px-2.5",
                                active
                                    ? "bg-primary/10 text-primary"
                                    : "text-sidebar-foreground/50 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                            )}
                        >
                            <item.icon size={17} className="shrink-0" />
                            <AnimatePresence>
                                {!collapsed && (
                                    <motion.span
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.12 }}
                                        className="font-mono text-xs tracking-widest uppercase whitespace-nowrap"
                                    >
                                        {item.label}
                                    </motion.span>
                                )}
                            </AnimatePresence>
                        </Link>
                    );

                    if (collapsed) {
                        return (
                            <Tooltip key={item.to}>
                                <TooltipTrigger render={link} />
                                <TooltipContent side="right">
                                    {item.label}
                                </TooltipContent>
                            </Tooltip>
                        );
                    }
                    return <div key={item.to}>{link}</div>;
                })}
            </nav>

            {/* Version tag — terminal feel */}
            <AnimatePresence>
                {!collapsed && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="px-4 pb-4 pt-2"
                    >
                        <span className="font-mono text-xs text-sidebar-foreground/30 tracking-widest">
                            v0.1.0
                        </span>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.aside>
    );
}
