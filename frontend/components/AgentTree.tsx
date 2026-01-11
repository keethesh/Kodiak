'use client';

import { ChevronRight, Circle, Activity } from 'lucide-react';

interface Agent {
    id: string;
    name: string;
    role: 'manager' | 'scout' | 'attacker';
    status: 'idle' | 'running' | 'paused' | 'failed';
    children?: Agent[];
}

interface AgentTreeProps {
    agents: Agent[];
    selectedAgentId: string;
    onSelectAgent: (id: string) => void;
}

export default function AgentTree({ agents, selectedAgentId, onSelectAgent }: AgentTreeProps) {

    const renderNode = (agent: Agent, level: number = 0) => {
        const isSelected = agent.id === selectedAgentId;

        return (
            <div key={agent.id} className="w-full">
                <div
                    onClick={() => onSelectAgent(agent.id)}
                    className={`
            flex items-center gap-2 py-2 px-3 cursor-pointer transition-all border-l-2
            ${isSelected ? 'bg-green-500/10 border-green-500 text-green-400' : 'border-transparent text-gray-500 hover:text-gray-300 hover:bg-white/5'}
          `}
                    style={{ paddingLeft: `${(level * 16) + 12}px` }}
                >
                    {/* Status Dot */}
                    <div className={`w-2 h-2 rounded-full shadow-[0_0_8px_currentColor] 
              ${agent.status === 'running' ? 'bg-green-500 text-green-500 animate-pulse' :
                            (agent.status === 'paused' ? 'bg-yellow-500 text-yellow-500' :
                                (agent.status === 'failed' ? 'bg-red-500 text-red-500' : 'bg-gray-700 text-gray-700'))}
           `} />

                    <span className="font-mono text-sm tracking-wide uppercase">{agent.name}</span>
                </div>

                {/* Children */}
                {agent.children && agent.children.map(child => renderNode(child, level + 1))}
            </div>
        );
    };

    return (
        <div className="w-full">
            <div className="px-4 py-3 border-b border-white/5">
                <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest flex items-center gap-2">
                    <Activity className="w-3 h-3" /> Swarm Intelligence
                </h3>
            </div>
            <div className="py-2">
                {agents.map(agent => renderNode(agent, 0))}
            </div>
        </div>
    );
}
