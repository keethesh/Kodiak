'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Terminal } from '@/components/Terminal';
import AgentTree from '@/components/AgentTree';
import HiveGraph from '@/components/HiveGraph';
import { useWebSocket } from '@/lib/useWebSocket';
import { getGraph, getProjects, createScan, startScan } from '@/lib/api';
import { LogMessage } from '@/types';
import { Activity, Shield, Cpu, Network, MessageSquare, ArrowLeft, Target, FileText, Play } from 'lucide-react';

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
    const [project, setProject] = useState<any>(null);
    // Scan State
    const [scanId, setScanId] = useState<string | null>(null);
    const [isConfigured, setIsConfigured] = useState(false);

    // Configuration Form State
    const [target, setTarget] = useState("");
    const [context, setContext] = useState("");

    // Mock Agent Data
    const [agents, setAgents] = useState([
        { id: 'Manager', name: 'Manager', role: 'manager', status: 'idle', children: [] }
    ]);

    // Load Project Data
    useEffect(() => {
        async function load() {
            if (!projectId) return;
            try {
                const projects = await getProjects();
                const proj = projects.find((p: any) => p.id === projectId);
                if (proj) {
                    setProject(proj);
                    // Ideally backend tells us if there is an active scan
                    // For MVP, we assume if logs exist, it's started ?? 
                    // Or we just check local state/graph.
                    const g = await getGraph(projectId);
                    setGraphData(g);
                    if (g.nodes.length > 0) setIsConfigured(true);
                }
            } catch (e) { }
        }
        load();
    }, [projectId]);

    // Connect to WS
    const { isConnected } = useWebSocket({
        scanId: projectId, // Currently mapping 1:1
        enabled: isConfigured, // Only connect if configured
        onMessage: (msg) => {
            if (msg.type === 'log') {
                setLogs(prev => [...prev, msg.payload as LogMessage]);
                // Auto update agent status if needed
                if (msg.payload.message.includes("Spawned")) {
                    // Logic to update tree dynamically?
                }
            }
            if (msg.type === 'tool_start') {
                setAgents(prev => {
                    // Basic status update mock
                    const newAgents = [...prev];
                    newAgents[0].status = 'running';
                    return newAgents;
                });
                setLogs(prev => [...prev, {
                    source: msg.data?.agent_id || "SYSTEM",
                    level: "INFO",
                    message: `> Executing: ${msg.data?.tool}`,
                    timestamp: new Date().toISOString()
                } as LogMessage]);
            }
        }
    });

    const handleStartMission = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            // Create a Scan Job and Start it
            // TODO: Update backend to associate Scan with Project properly if not automatic
            // For now, createScan maps 1:1
            await createScan(project.name + "_SCAN", target, context);
            // await startScan(projectId); // Assuming create auto-starts or we use ID
            setIsConfigured(true);
            // Initial Log
            setLogs([{
                source: "SYSTEM",
                level: "INFO",
                message: `MISSION INITIALIZED. TARGET: ${target}`,
                timestamp: new Date().toISOString()
            }]);
        } catch (err) {
            console.error(err);
            // For MVP, if create fails, maybe it already exists, just proceed
            setIsConfigured(true);
        }
    };

    if (!project) return <div className="text-center p-20 text-gray-500 font-mono">LOADING_ENCRYPTED_DATA...</div>;

    return (
        <div className="flex h-screen bg-[#050505] text-[#e0e0e0] font-mono overflow-hidden">

            {/* LEFT: Feed Section (Flexible Width) */}
            <main className="flex-1 flex flex-col border-r border-[#1a1a1a] relative">
                {/* Header */}
                <header className="h-16 border-b border-[#1a1a1a] flex items-center justify-between px-6 bg-[#0a0a0a]">
                    <div>
                        <h2 className="text-lg font-bold flex items-center gap-3">
                            <span className={`w-2 h-2 rounded-full ${(isConnected || !isConfigured) ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
                            MISSION_STATUS // {project.name.toUpperCase()}
                        </h2>
                    </div>

                    {isConfigured && (
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
                    )}

                    <button onClick={() => router.push('/')} className="px-3 py-1 border border-red-500/30 text-red-500 text-xs hover:bg-red-500/10 rounded-sm flex items-center gap-2">
                        <ArrowLeft size={12} /> EJECT
                    </button>
                </header>

                {/* Content Area */}
                <div className="flex-1 relative bg-black/50">
                    {!isConfigured ? (
                        // SETUP MODE
                        <div className="absolute inset-0 flex items-center justify-center p-8 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-green-900/10 via-[#050505] to-[#050505]">
                            <div className="w-full max-w-2xl bg-[#0a0a0a] border border-[#333] rounded-lg p-8 shadow-2xl">
                                <h3 className="text-2xl font-bold mb-6 text-white flex items-center gap-3 border-b border-[#333] pb-4">
                                    <Target className="text-green-500" /> MISSION_CONFIGURATION
                                </h3>
                                <form onSubmit={handleStartMission} className="space-y-6">
                                    <div>
                                        <label className="block text-sm font-bold text-gray-500 mb-2 uppercase tracking-wide">Primary Target</label>
                                        <input
                                            className="w-full bg-[#111] border border-[#333] text-white p-4 rounded text-lg font-mono focus:border-green-500 outline-none"
                                            placeholder="e.g. 192.168.1.5 or example.com"
                                            value={target}
                                            onChange={e => setTarget(e.target.value)}
                                            required
                                            autoFocus
                                        />
                                        <p className="text-xs text-gray-600 mt-2">Domain, IP, or CIDR to target.</p>
                                    </div>

                                    <div>
                                        <label className="block text-sm font-bold text-gray-500 mb-2 uppercase tracking-wide">Context / Intel</label>
                                        <textarea
                                            className="w-full bg-[#111] border border-[#333] text-white p-4 rounded font-mono focus:border-green-500 outline-none h-32"
                                            placeholder="Known open ports, technology stack, goal of the engagement..."
                                            value={context}
                                            onChange={e => setContext(e.target.value)}
                                        />
                                    </div>

                                    <button type="submit" className="w-full bg-green-600 hover:bg-green-500 text-black font-bold py-4 rounded text-lg flex items-center justify-center gap-3 transition-all hover:shadow-[0_0_30px_rgba(34,197,94,0.4)]">
                                        <Play fill="black" /> COMMENCE_MISSION
                                    </button>
                                </form>
                            </div>
                        </div>
                    ) : (
                        // ACTIVE MODE
                        <>
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
                        </>
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
                                {/* Mock finding count */}
                                {graphData.nodes.filter((n: any) => n.group === 'finding').length} <Shield size={14} className="text-green-500" />
                            </div>
                        </div>
                        <div className="bg-[#111] p-2 rounded border border-[#222]">
                            <div className="text-[10px] text-gray-500">TOKENS</div>
                            <div className="text-xl font-bold text-white">---</div>
                        </div>
                    </div>

                    <div className="space-y-2 text-xs font-mono text-gray-400">
                        <div className="flex justify-between">
                            <span>MODEL</span>
                            <span className="text-green-500">gemini-1.5-pro</span>
                        </div>
                        <div className="flex justify-between">
                            <span>COST</span>
                            <span className="text-yellow-500">$0.00</span>
                        </div>
                        <div className="flex justify-between">
                            <span>LATENCY</span>
                            <span>14ms</span>
                        </div>
                    </div>
                </div>

            </aside>
        </div>
    );
}
