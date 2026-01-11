'use client';

import { useEffect, useRef } from 'react';
import { Network } from 'vis-network';
import { DataSet } from 'vis-data'; // Need to insure vis-data is available, usually comes with vis-network
// Note: standard import 'vis-network' might include everything. 
// If specific imports fail, we fall back to: import { Network } from 'vis-network/standalone';

interface GraphNode {
    id: string;
    label: string;
    group: string;
    value?: number;
    metadata?: any;
}

interface GraphLink {
    source: string;
    target: string;
    label?: string;
}

interface HiveGraphProps {
    nodes: GraphNode[];
    links: GraphLink[];
}

export default function HiveGraph({ nodes, links }: HiveGraphProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const networkRef = useRef<Network | null>(null);

    useEffect(() => {
        if (!containerRef.current) return;

        // Transform Data
        const visNodes = new DataSet(nodes.map(n => ({
            id: n.id,
            label: n.label,
            group: n.group,
            value: n.value || 5,
            // Styling per group
            color: n.group === 'domain' ? '#00ff41' : (n.group === 'finding' ? '#ff3333' : '#0088ff'),
            shape: 'dot',
            font: { color: '#e0e0e0', face: 'monospace' }
        })));

        const visEdges = new DataSet(links.map(l => ({
            id: `${l.source}-${l.target}`, // Fix: vis-data DataSet requires an 'id'
            from: l.source,
            to: l.target,
            label: l.label,
            arrows: 'to',
            color: { color: '#333' }
        })));

        const data = { nodes: visNodes, edges: visEdges };

        const options = {
            nodes: {
                borderWidth: 1,
                borderWidthSelected: 2,
                shadow: true,
            },
            edges: {
                width: 1,
                shadow: false,
                smooth: {
                    type: 'continuous'
                }
            },
            physics: {
                stabilization: false,
                barnesHut: {
                    gravitationalConstant: -8000,
                    springConstant: 0.04,
                    springLength: 95
                },
            },
            interaction: {
                hover: true,
                tooltipDelay: 200,
                zoomView: true
            },
            height: '100%',
            width: '100%'
        };

        // Explicitly assert data type to match vis-network's expected loose types if needed
        // but adding 'id' usually solves the structure mismatch.
        // @ts-ignore
        const networkData = { nodes: visNodes, edges: visEdges };

        // Initialize Network
        // @ts-ignore - vis-network types can be finicky
        // Initialize Network
        // @ts-ignore
        networkRef.current = new Network(containerRef.current, networkData, options);

        return () => {
            if (networkRef.current) {
                networkRef.current.destroy();
                networkRef.current = null;
            }
        };
    }, [nodes, links]); // Re-render when data changes

    return (
        <div className="w-full h-full bg-[#050505] relative border-t border-[#1a1a1a]">
            <div ref={containerRef} className="absolute inset-0" />

            <div className="absolute top-4 left-4 p-2 bg-black/80 border border-green-500/20 rounded text-xs text-green-500 font-mono">
                NODES: {nodes.length} | LINKS: {links.length}
            </div>
        </div>
    );
}
