'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Terminal } from '@/components/Terminal';
import AgentTree from '@/components/AgentTree';
import HiveGraph from '@/components/HiveGraph';
import { useWebSocket } from '@/lib/useWebSocket';
import { getGraph, getProjects } from '@/lib/api';
import { LogMessage } from '@/types';
import { Activity, Shield, Cpu, Network, MessageSquare, ArrowLeft } from 'lucide-react';

export default function MissionHUD() {
    const params = useParams();
    const router = useRouter();
    const projectId = params?.id as string;

    // Tabs
    const [activeTab, setActiveTab] = useState<'feed' | 'hive'>('feed');

    // Data State
    const [logs, setLogs] = useState<LogMessage[]>([]);
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [selectedAgent, setSelectedAgent] = useState<string>("Manager");

    // Project Meta
    const [projectName, setProjectName] = useState("LOADING...");

    // Mock Agent Data (Prototype)
    // In real implementation, this would come from a "swarms" API or websocket updates
    const [agents, setAgents] = useState([
        {
            id: 'Manager', name: 'Manager', role: 'manager', status: 'running', children: [
                { id: 'Scout', name: 'Scout (Recon)', role: 'scout', status: 'running' },
                { id: 'Attacker', name: 'Attacker (Exploit)', role: 'attacker', status: 'idle' }
            ]
        }
    ]);

    // Load Project Data
    useEffect(() => {
        async function load() {
            if (!projectId) return;

            // Fetch Project Name (inefficient to fetch all, but MVP)
            try {
                const projects = await getProjects();
                const proj = projects.find((p: any) => p.id === projectId);
                if (proj) setProjectName(proj.name);
            } catch (e) { }

            // Fetch Graph
            try {
                const g = await getGraph(projectId);
                setGraphData(g);
            } catch (e) { }
        }
        load();
    }, [projectId]);

    // Connect to WS
    const { isConnected } = useWebSocket({
        scanId: projectId, // We map Project ID to Scan ID for now 1:1
        enabled: true,
        onMessage: (msg) => {
            if (msg.type === 'log') {
                setLogs(prev => [...prev, msg.payload as LogMessage]);
            }
            // Handle tool_start/complete events to update Agent Status visual?
            // For now, we just log them
            if (msg.type === 'tool_start') {
                setLogs(prev => [...prev, {
                    source: msg.data?.agent_id || "SYSTEM",
                    level: "INFO",
                    message: `> Executing: ${msg.data?.tool}`,
                    timestamp: new Date().toISOString()
                } as LogMessage]);
            }
        }
    });

    return (
        <div className="flex h-screen bg-[#050505] text-[#e0e0e0] font-mono overflow-hidden">

            {/* LEFT: Feed Section (Flexible Width) */}
            <main className="flex-1 flex flex-col border-r border-[#1a1a1a] relative">
                {/* Header */}
                <header className="h-16 border-b border-[#1a1a1a] flex items-center justify-between px-6 bg-[#0a0a0a]">
                    <div>
                        <h2 className="text-lg font-bold flex items-center gap-3">
                            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
                            MISSION_STATUS // {projectName.toUpperCase()}
                        </h2>
                    </div>

                    {/* Tabs */}
                    <div className="flex bg-[#111] rounded-sm p-1 gap-1">
                        <button
                            onClick={() => setActiveTab('feed')}
                            className={`px-4 py-1 text-xs font-bold rounded-sm transition-all ${activeTab === 'feed' ? 'bg-green-600 text-black shadow-[0_0_10px_rgba(34,197,94,0.4)]' : 'text-gray-500 hover:text-white'}`}
                        >
                            LIVE_FEED
                        </button>
                        <button
                            onClick={() => setActiveTab('hive')}
                            className={`px-4 py-1 text-xs font-bold rounded-sm transition-all ${activeTab === 'hive' ? 'bg-green-600 text-black shadow-[0_0_10px_rgba(34,197,94,0.4)]' : 'text-gray-500 hover:text-white'}`}
                        >
                            HIVE_MIND
                        </button>
                    </div>

                    <button onClick={() => router.push('/')} className="px-3 py-1 border border-red-500/30 text-red-500 text-xs hover:bg-red-500/10 rounded-sm flex items-center gap-2">
                        <ArrowLeft size={12} /> EJECT
                    </button>
                </header>

                {/* Content Area */}
                <div className="flex-1 relative bg-black/50">
                    {activeTab === 'feed' && (
                        <div className="absolute inset-0 p-0">
                            <Terminal
                                logs={logs.filter(l => selectedAgent === 'Manager' || (l.source && l.source.includes(selectedAgent)))}
                                title={`COMMS_UPLINK :: ${selectedAgent.toUpperCase()}`}
                                className="h-full border-none rounded-none"
                            />

                            {/* Chat Bar Overlay */}
                            <div className="absolute bottom-6 left-6 right-6">
                                <div className="relative">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-green-500">
                                        <MessageSquare size={16} />
                                    </div>
                                    <input
                                        type="text"
                                        placeholder={`Transmit instructions to ${selectedAgent}...`}
                                        className="w-full bg-black/90 border border-green-500/30 rounded-md py-3 pl-10 pr-4 text-sm text-green-100 placeholder-green-700/50 focus:border-green-500 focus:ring-1 focus:ring-green-500 outline-none shadow-[0_0_20px_rgba(0,0,0,0.5)] backdrop-blur-md"
                                    />
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'hive' && (
                        <div className="absolute inset-0 bg-[#050505]">
                            <HiveGraph nodes={graphData.nodes} links={graphData.links} />
                        </div>
                    )}
                </div>
            </main>

            {/* RIGHT: Sidebar (Fixed Width) */}
            <aside className="w-80 bg-[#0a0a0a] flex flex-col border-l border-[#1a1a1a]">

                {/* Agent Tree */}
                <div className="flex-1 overflow-y-auto">
                    <AgentTree
                        agents={agents as any}
                        selectedAgentId={selectedAgent}
                        onSelectAgent={setSelectedAgent}
                    />
                </div>

                {/* Stats / System Info */}
                <div className="p-4 border-t border-[#1a1a1a] bg-[#080808]">
                    <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <Cpu size={14} /> System Telemetry
                    </h3>

                    <div className="grid grid-cols-2 gap-2 mb-4">
                        <div className="bg-[#111] p-2 rounded border border-[#222]">
                            <div className="text-[10px] text-gray-500">VULNERABILITIES</div>
                            <div className="text-xl font-bold text-white flex items-center gap-2">
                                0 <Shield size={14} className="text-green-500" />
                            </div>
                        </div>
                        <div className="bg-[#111] p-2 rounded border border-[#222]">
                            <div className="text-[10px] text-gray-500">TOKENS</div>
                            <div className="text-xl font-bold text-white">12.5k</div>
                        </div>
                    </div>

                    <div className="space-y-2 text-xs font-mono text-gray-400">
                        <div className="flex justify-between">
                            <span>MODEL</span>
                            <span className="text-green-500">gemini-1.5-pro</span>
                        </div>
                        <div className="flex justify-between">
                            <span>COST</span>
                            <span className="text-yellow-500">$0.142</span>
                        </div>
                        <div className="flex justify-between">
                            <span>LATENCY</span>
                            <span>142ms</span>
                        </div>
                    </div>
                </div>

            </aside>
        </div>
    );
}
