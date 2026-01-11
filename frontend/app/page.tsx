'use client';

import { useState, useEffect } from 'react';
import { Terminal } from '@/components/Terminal';
import { useWebSocket } from '@/lib/useWebSocket';
import { LogMessage } from '@/types';
import { Play, Pause } from 'lucide-react';

import { startScan, createScan } from '@/lib/api';

export default function Home() {
  const [logs, setLogs] = useState<LogMessage[]>([]);

  // Hardcoded for demo - in reality, we'd create a scan first
  const [scanId, setScanId] = useState<string>("demo-scan-1");
  const [isStarted, setIsStarted] = useState(false);

  // Connect to WS
  const { isConnected, sendMessage } = useWebSocket({
    scanId,
    enabled: true,
    onMessage: (msg) => {
      // If we receive a log message
      if (msg.type === 'log') {
        const payload = msg.payload as LogMessage; // or whatever the backend sends
        // Backend actually sends 'log' type for logs.
        // Let's assume payload matches LogMessage or map it
        setLogs(prev => [...prev, payload]);
      }
    }
  });

  const handleStart = async () => {
    setIsStarted(true);
    // In a real app, calls POST /api/v1/scans/{id}/start
    // For demo, effectively doing nothing but UI state

    // Simulate some local logs for effect if offline
    if (!isConnected) {
      addLog("SYSTEM", "WARNING", "Backend Disconnected. Running Demo Mode.");
      setTimeout(() => addLog("ORCH", "INFO", "Initializing Scan..."), 500);
      setTimeout(() => addLog("NMAP", "INFO", "Scanning 192.168.1.1..."), 1200);
    }
  };

  const addLog = (source: string, level: any, message: string) => {
    setLogs(prev => [...prev, {
      scan_id: scanId,
      level,
      message,
      source,
      timestamp: new Date().toISOString()
    }]);
  }

  return (
    <div className="min-h-screen bg-black text-gray-200 p-8 font-sans selection:bg-green-500/30">
      <main className="max-w-6xl mx-auto space-y-8">

        {/* Hero Section */}
        <div className="flex justify-between items-end border-b border-green-900/30 pb-6">
          <div>
            <h1 className="text-4xl font-black tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-green-500 to-emerald-700">
              KODIAK
            </h1>
            <p className="text-green-500/50 mt-2 font-mono text-sm">
              AI-POWERED OFFENSIVE SECURITY SUITE
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${isConnected ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'}`}>
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              {isConnected ? 'HIVE MIND: ONLINE' : 'HIVE MIND: OFFLINE'}
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1: Target */}
          <div className="bg-zinc-900/50 border border-white/5 rounded-xl p-6">
            <label className="text-xs font-bold text-gray-500 uppercase tracking-widest">Target Scope</label>
            <div className="mt-2 text-2xl font-mono text-white">scanme.nmap.org</div>
          </div>

          {/* Card 2: Status */}
          <div className="bg-zinc-900/50 border border-white/5 rounded-xl p-6">
            <label className="text-xs font-bold text-gray-500 uppercase tracking-widest">Operation Status</label>
            <div className="mt-2 text-2xl font-mono text-white flex items-center gap-2">
              {isStarted ? <span className="text-green-400">RUNNING</span> : <span className="text-zinc-500">IDLE</span>}
            </div>
          </div>

          {/* Card 3: Action */}
          <button
            onClick={handleStart}
            disabled={isStarted}
            className="group bg-gradient-to-br from-green-600 to-green-800 hover:from-green-500 hover:to-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl p-6 flex items-center justify-center transition-all shadow-[0_0_20px_rgba(34,197,94,0.2)] hover:shadow-[0_0_30px_rgba(34,197,94,0.4)]"
          >
            {isStarted ? (
              <Pause className="w-8 h-8 text-white fill-current" />
            ) : (
              <Play className="w-8 h-8 text-white fill-current" />
            )}
          </button>
        </div>

        {/* Terminal */}
        <Terminal logs={logs} className="h-[500px]" />

      </main>
    </div>
  );
}
