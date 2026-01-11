'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Folder, Activity, Shield } from 'lucide-react';
import { getProjects, createProject } from '@/lib/api';

interface Project {
  id: string;
  name: string;
  files: any[];
  status: string;
  description?: string;
}

export default function ProjectManager() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [showModal, setShowModal] = useState(false);

  // Form State
  const [pName, setPName] = useState("");

  const refresh = async () => {
    try {
      const data = await getProjects();
      setProjects(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // Simplified Creation: Name Only
      const newProj = await createProject(pName);
      setShowModal(false);
      setPName("");
      // Redirect immediately to Mission HUD for setup
      router.push(`/mission/${newProj.id}`);
    } catch (err) {
      alert("Failed to create project. Check backend connectivity.");
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] text-[#e0e0e0] font-mono p-8 selection:bg-green-500/30">
      <header className="flex justify-between items-center mb-12 border-b border-[#1a1a1a] pb-6">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-green-500/10 border border-green-500 rounded-sm flex items-center justify-center">
            <Shield className="text-green-500 w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tighter text-white">KODIAK_v2</h1>
            <p className="text-xs text-green-500/50 tracking-[0.2em] font-bold">OFFENSIVE SWARM INTELLIGENCE</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 rounded bg-gray-900 border border-gray-800 flex items-center justify-center text-xs font-bold text-gray-500">
            ADM
          </div>
        </div>
      </header>

      <main>
        <div className="flex justify-between items-end mb-8">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Folder className="text-gray-500" size={20} />
            ENGAGEMENTS
          </h2>
          <button
            onClick={() => setShowModal(true)}
            className="bg-green-600 hover:bg-green-500 text-black font-bold px-4 py-2 rounded-sm text-sm flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(34,197,94,0.3)] hover:shadow-[0_0_25px_rgba(34,197,94,0.5)]"
          >
            <Plus size={16} /> NEW_PROJECT
          </button>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map(p => (
            <div
              key={p.id}
              onClick={() => router.push(`/mission/${p.id}`)}
              className="group relative bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-6 hover:border-green-500/50 transition-all cursor-pointer hover:bg-[#0f0f0f]"
            >
              <div className="flex justify-between items-start mb-4">
                <div className="px-2 py-1 text-[10px] font-bold rounded border border-gray-700 text-gray-500">
                  IDLE
                </div>
                <Activity size={16} className="text-gray-700 group-hover:text-green-500 transition-colors" />
              </div>

              <h3 className="text-lg font-bold text-white mb-2 group-hover:text-green-400 transition-colors">{p.name}</h3>
              <p className="text-xs text-gray-500 mb-6 font-sans truncate">{p.id}</p>

              <div className="absolute bottom-0 left-0 w-full h-[2px] bg-green-500 transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left"></div>
            </div>
          ))}

          {projects.length === 0 && (
            <div className="col-span-full py-20 text-center text-gray-600 border border-dashed border-[#1a1a1a] rounded-lg">
              NO ACTIVE ENGAGEMENTS
            </div>
          )}
        </div>
      </main>

      {/* Simplified Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0a0a0a] border border-[#333] w-full max-w-md rounded-lg shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="p-6 border-b border-[#1a1a1a] flex justify-between items-center">
              <h3 className="text-lg font-bold text-white">INITIALIZE_ENGAGEMENT</h3>
              <button onClick={() => setShowModal(false)} className="text-gray-500 hover:text-white"><Plus className="rotate-45" /></button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">PROJECT_NAME</label>
                <input
                  value={pName}
                  onChange={e => setPName(e.target.value)}
                  className="w-full bg-[#111] border border-[#333] rounded px-3 py-2 text-white focus:border-green-500 outline-none transition-colors"
                  placeholder="e.g. Operation Blackbriar"
                  required
                  autoFocus
                />
              </div>

              <div className="pt-4 flex justify-end gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="px-4 py-2 text-gray-400 hover:text-white text-sm">CANCEL</button>
                <button type="submit" className="bg-green-600 hover:bg-green-500 text-black font-bold px-6 py-2 rounded-sm text-sm">CREATE & CONFIGURE &rarr;</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
