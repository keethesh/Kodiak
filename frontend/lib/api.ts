const API_BASE = process.env.NEXT_PUBLIC_WS_URL?.replace('ws://', 'http://').replace('wss://', 'https://') || 'http://localhost:8000/api/v1';

export async function startScan(scanId: string) {
    const res = await fetch(`${API_BASE}/scans/${scanId}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error('Failed to start scan');
    return res.json();
}

export async function stopScan(scanId: string) {
    const res = await fetch(`${API_BASE}/scans/${scanId}/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error('Failed to stop scan');
    return res.json();
}

export async function createScan(name: string, target: string, instructions: string = "") {
    const res = await fetch(`${API_BASE}/scans/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            config: {
                target,
                instructions
            }
        })
    });
    if (!res.ok) throw new Error('Failed to create scan');
    return res.json();
}

export async function getProjects() {
    const res = await fetch(`${API_BASE}/projects/`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    return res.json();
}

export async function createProject(name: string) {
    // Only send name, let backend handle ID/Defaults
    // We do NOT send status/description as they are optional/defaulted
    const res = await fetch(`${API_BASE}/projects/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name
        })
    });
    if (!res.ok) throw new Error('Failed to create project');
    return res.json();
}

export async function getGraph(projectId: string) {
    const res = await fetch(`${API_BASE}/graph/${projectId}`);
    if (!res.ok) return { nodes: [], links: [] };
    return res.json();
}

export async function getApprovals() {
    const res = await fetch(`${API_BASE}/approvals/pending`);
    if (!res.ok) return [];
    return res.json();
}

export async function resolveApproval(taskId: string, action: 'approve' | 'deny') {
    const res = await fetch(`${API_BASE}/approvals/${taskId}/${action}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to resolve approval');
    return res.json();
}
