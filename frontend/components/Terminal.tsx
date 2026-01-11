'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal as TerminalIcon, Minimize2, Maximize2, X } from 'lucide-react';
import { clsx } from 'clsx';
import { LogMessage } from '@/types';

interface TerminalProps {
    logs: LogMessage[];
    className?: string;
    title?: string;
}

export const Terminal: React.FC<TerminalProps> = ({ logs, className, title = "KODIAK_CLAYMORE_Tv1.0" }) => {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [autoScroll, setAutoScroll] = useState(true);

    // Auto-scroll to bottom
    useEffect(() => {
        if (autoScroll && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs, autoScroll]);

    // Handle scroll events to pause auto-scroll
    const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
        const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
        const isAtBottom = scrollHeight - scrollTop === clientHeight;
        setAutoScroll(isAtBottom);
    };

    return (
        <div className={clsx(
            "flex flex-col bg-black/90 border border-green-500/30 rounded-lg overflow-hidden font-mono text-sm shadow-[0_0_20px_rgba(34,197,94,0.1)] backdrop-blur-sm",
            className
        )}>
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 bg-green-900/10 border-b border-green-500/20">
                <div className="flex items-center gap-2 text-green-500">
                    <TerminalIcon size={16} />
                    <span className="font-bold tracking-wider text-xs opacity-80">{title}</span>
                </div>
                <div className="flex items-center gap-2 opacity-50">
                    <Minimize2 size={14} className="cursor-pointer hover:text-green-400" />
                    <Maximize2 size={14} className="cursor-pointer hover:text-green-400" />
                    <X size={14} className="cursor-pointer hover:text-red-400" />
                </div>
            </div>

            {/* Body */}
            <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto p-4 space-y-1 scrollbar-thin scrollbar-thumb-green-500/20 scrollbar-track-transparent h-[400px]"
            >
                <AnimatePresence initial={false}>
                    {logs.map((log, index) => (
                        <motion.div
                            key={`${log.timestamp}-${index}`}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.2 }}
                            className={clsx(
                                "flex gap-3 font-mono",
                                log.level === 'ERROR' ? "text-red-500" :
                                    log.level === 'WARNING' ? "text-yellow-500" :
                                        log.level === 'DEBUG' ? "text-blue-400 opacity-60" :
                                            "text-green-400"
                            )}
                        >
                            <span className="opacity-50 text-xs min-w-[120px]">{new Date(log.timestamp).toLocaleTimeString()}</span>
                            <span className="font-bold min-w-[80px] text-xs">[{log.source}]</span>
                            <span className="flex-1 break-all">{log.message}</span>
                        </motion.div>
                    ))}
                    {logs.length === 0 && (
                        <div className="text-green-500/30 italic text-center mt-20">
                            System Ready... Awaiting Input...
                        </div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
};
